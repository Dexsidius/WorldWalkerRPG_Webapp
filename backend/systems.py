"""Deterministic campaign subsystems used around AI-authored narration.

These helpers keep long-campaign memory, world clocks, quest structure,
progression tuning, map planning, and health diagnostics stable even when a
smaller narrator model omits optional bookkeeping.
"""
import copy
import math
import random
import re
import secrets

from util import ai_text
from causality import advance_causal_clock

# A chapter is meant to read as a season of the story, not a fixed number of
# actions — consolidate roughly every in-game quarter (90 days on the
# standard 30-day-month calendar) rather than every few turns, so chapter
# count tracks how much story time has actually passed. The beat-count
# backstop exists only for a campaign that lingers a long time without much
# date movement (heavy dialogue, a single extended scene), so chapters still
# happen eventually even then.
CHAPTER_SPAN_DAYS = 90
CHAPTER_BEAT_BACKSTOP = 24


WORLD_PROGRESSION_PRESETS = {
    "One Piece": {"label": "Will and hard-won mastery", "training_rate": 1.08, "breakthrough_rate": 1.10, "xp_rate": 0.0, "travel_scale": 1.45},
    "Hunter x Hunter": {"label": "Nen fundamentals and deliberate conditions", "training_rate": .92, "breakthrough_rate": .85, "xp_rate": 0.0, "travel_scale": 1.10},
    "Naruto": {"label": "Chakra practice, missions, and instruction", "training_rate": 1.00, "breakthrough_rate": 1.00, "xp_rate": 0.0, "travel_scale": 1.00},
    "Solo Max-Level Newbie": {"label": "Tower XP and achievement progression", "training_rate": .88, "breakthrough_rate": 1.05, "xp_rate": 1.18, "travel_scale": .85},
    "Overgeared": {"label": "Satisfy XP, classes, affinity, and production mastery", "training_rate": .95, "breakthrough_rate": 1.08, "xp_rate": 1.10, "travel_scale": .90},
    "Reincarnated as a Slime": {"label": "Skills, magicules, naming, and evolution", "training_rate": 1.04, "breakthrough_rate": .92, "xp_rate": 0.0, "travel_scale": 1.05},
    "Bleach": {"label": "Zanjutsu drills, Kido study, and a bond with one's Zanpakuto", "training_rate": .96, "breakthrough_rate": .90, "xp_rate": 0.0, "travel_scale": 1.05},
    "Custom World": {"label": "Setting-defined growth", "training_rate": 1.00, "breakthrough_rate": 1.00, "xp_rate": 1.00, "travel_scale": 1.00},
}


WORLD_TERRITORIES = {
    "One Piece": {"Shells Town": "Marines", "Loguetown": "Marines", "Enies Lobby": "World Government", "Sabaody": "World Government", "Arlong Park": "Pirates",
                  "Fishman Island": "Whitebeard Pirates", "Totto Land": "Big Mom Pirates", "Wano Country": "Kaido's Beasts Pirates",
                  "Marineford": "Marines", "Impel Down": "World Government"},
    "Hunter x Hunter": {"Hunter Exam Site": "Hunter Association", "Hunter Association HQ": "Hunter Association", "Meteor City": "Phantom Troupe", "Kukuroo Mountain": "Zoldyck Family", "Yorknew City": "Yorknew Mafia"},
    "Naruto": {"Konohagakure": "Konohagakure", "Sunagakure": "Sunagakure", "Kirigakure": "Kirigakure", "Kumogakure": "Kumogakure", "Iwagakure": "Iwagakure",
               "Amegakure": "Amegakure", "Iron Country": "Iron Country"},
    "Solo Max-Level Newbie": {"Earth — Tower Entrance": "Players", "Floor 10": "Tower Administrators", "Floor 20": "Tower Administrators", "Floor 30": "Tower Administrators", "Floor 40": "Tower Administrators", "Floor 50+": "Tower Administrators"},
    "Overgeared": {"Winston": "Local Lords", "Titan": "Kingdom", "Saharan Empire": "Kingdom", "Reidan": "Guilds"},
    "Reincarnated as a Slime": {"Great Jura Forest": "Jura Forest Monsters", "Goblin Village": "Jura Forest Monsters", "Tempest": "Jura Forest Monsters", "Kingdom of Falmuth": "Kingdom of Falmuth", "Demon Lord's Domain": "Demon Lords"},
    # Hueco Mundo/Las Noches deliberately have no controller seeded here —
    # at this world's default campaign start (pre-Aizen-reveal), who
    # actually holds it isn't public knowledge yet, and seeding one would
    # spoil the Soul Society arc's own twist before the story gets there.
    "Bleach": {"Seireitei": "Gotei 13", "Rukongai": "Gotei 13", "Shin'o Academy": "Gotei 13",
               "Senzaikyu": "Central 46", "Central 46 Chambers": "Central 46"},
    "Custom World": {"Starting Region": "Local Faction"},
}


def progression_preset_for(world):
    return copy.deepcopy(WORLD_PROGRESSION_PRESETS.get(world, WORLD_PROGRESSION_PRESETS["Custom World"]))


def default_tuning_for(world):
    preset = progression_preset_for(world)
    return {
        "check_warning_threshold": 65,
        "xp_rate": preset["xp_rate"] if preset["xp_rate"] else 1.0,
        "training_rate": preset["training_rate"],
        "breakthrough_rate": preset["breakthrough_rate"],
        "combat_danger": 1.0,
        "resource_pressure": 1.0,
    }


def normalize_tuning(state):
    defaults = default_tuning_for(state.get("world", "Custom World"))
    current = state.get("difficulty_controls") if isinstance(state.get("difficulty_controls"), dict) else {}
    clean = {}
    for key, default in defaults.items():
        try:
            value = float(current.get(key, default))
        except (TypeError, ValueError):
            value = default
        if key == "check_warning_threshold":
            clean[key] = int(max(40, min(95, value)))
        else:
            clean[key] = round(max(.5, min(2.0, value)), 2)
    state["difficulty_controls"] = clean
    state["progression_preset"] = progression_preset_for(state.get("world", "Custom World"))
    return clean


def _list(value):
    if isinstance(value, list): return value
    if value in (None, ""): return []
    return [value]


def normalize_quest_state_machine(state):
    """Upgrade active quests into explicit objective/branch state."""
    completed = []
    for quest in state.get("quests", []):
        if not isinstance(quest, dict):
            continue
        raw_objectives = quest.get("objectives")
        if not isinstance(raw_objectives, list) or not raw_objectives:
            raw_objectives = quest.get("clear_conditions") or quest.get("conditions") or []
        objectives = []
        for index, raw in enumerate(_list(raw_objectives)):
            if isinstance(raw, dict):
                text = str(raw.get("text") or raw.get("name") or raw.get("objective") or f"Objective {index + 1}")[:500]
                status = str(raw.get("status") or ("complete" if raw.get("complete") else "active")).lower()
                objectives.append({"id": str(raw.get("id") or f"obj-{index + 1}"), "text": text,
                                   "status": status if status in {"active", "complete", "failed", "locked"} else "active",
                                   "optional": bool(raw.get("optional")), "progress": max(0, min(100, int(raw.get("progress", 100 if status == "complete" else 0) or 0)))})
            else:
                objectives.append({"id": f"obj-{index + 1}", "text": str(raw)[:500], "status": "active", "optional": False, "progress": 0})
        quest["objectives"] = objectives
        quest["completion_conditions"] = [obj["text"] for obj in objectives if not obj.get("optional")]
        quest["optional_objectives"] = [obj["text"] for obj in objectives if obj.get("optional")]
        quest["discovered_clues"] = _list(quest.get("discovered_clues") or quest.get("current_knowledge") or quest.get("evidence"))
        quest["current_obstacles"] = _list(quest.get("current_obstacles") or quest.get("risks"))
        quest["next_hint"] = str(quest.get("next_hint") or quest.get("first_step") or
                                 (f"Continue working on: {next((o['text'] for o in objectives if o['status'] == 'active'), 'the next known lead')}") )[:500]
        required_progress = [obj.get("progress", 0) for obj in objectives if not obj.get("optional")]
        quest["progress_percent"] = round(sum(required_progress) / len(required_progress)) if required_progress else 0
        required = [obj for obj in objectives if not obj.get("optional")]
        branch = quest.get("branch_state") if isinstance(quest.get("branch_state"), dict) else {}
        branch.setdefault("current", "main")
        branch["available"] = [str(x)[:300] for x in _list(branch.get("available")) if str(x).strip()]
        branch["locked"] = [str(x)[:300] for x in _list(branch.get("locked")) if str(x).strip()]
        # A quest without choices is an isolated checklist.  Seed two grounded
        # routes from its own briefing, then unlock the confrontation route as
        # earlier required objectives are completed.  This is deterministic
        # scaffolding; the narrator can replace or enrich it with specific
        # world-authored branches on later turns.
        if not branch["available"] and not branch["locked"]:
            locations = _list(quest.get("locations") or quest.get("location"))
            giver = str(quest.get("giver") or quest.get("cause") or "the quest giver").strip()
            lead = str(quest.get("next_hint") or quest.get("first_step") or "the primary lead").strip()
            branch["available"] = [f"Follow the primary lead: {lead}"[:300]]
            alternate = (f"Seek an alternate route through {giver}" if giver else
                         f"Investigate an alternate route at {locations[0]}" if locations else "Search for an alternate source")
            if alternate.lower() not in {x.lower() for x in branch["available"]}:
                branch["available"].append(alternate[:300])
            if required:
                branch["locked"] = [f"Directly resolve: {required[-1]['text']}"[:300]]
        completed_required = [obj for obj in objectives if not obj.get("optional") and obj.get("status") == "complete"]
        if completed_required and branch["locked"]:
            unlocked = branch["locked"].pop(0)
            if unlocked.lower() not in {x.lower() for x in branch["available"]}:
                branch["available"].append(unlocked)
        branch["routes"] = [
            {"name": name, "status": "available", "consequence": "Choosing this route may close or alter competing approaches."}
            for name in branch["available"]
        ] + [
            {"name": name, "status": "locked", "consequence": "Complete an earlier objective or discover the missing prerequisite."}
            for name in branch["locked"]
        ]
        quest["branch_state"] = branch
        quest.setdefault("consequences", [])
        if required and all(obj.get("status") == "complete" for obj in required):
            quest["status"] = "Completed"
            completed.append(quest.get("name", "Quest"))
    return completed


def update_chapter_memory(before, state, trigger, narrative):
    turn = int(state.get("turn", 0) or 0)
    canon_day = int(state.get("canon_day", 0) or 0)
    clean_narrative = re.sub(r"\s+", " ", str(narrative or "The world moved forward.")).strip()[:650]
    changes = []
    if before.get("location") != state.get("location"):
        changes.append(f"Moved to {state.get('location')}.")
    old_titles = set(ai_text(t) for t in before.get("titles", []) if ai_text(t))
    new_titles = set(ai_text(t) for t in state.get("titles", []) if ai_text(t))
    if new_titles - old_titles: changes.append("Titles: " + ", ".join(sorted(new_titles - old_titles)))
    old_skills, new_skills = set(before.get("skills", {})), set(state.get("skills", {}))
    if new_skills - old_skills: changes.append("Skills: " + ", ".join(sorted(new_skills - old_skills)))
    old_quests = {str(q.get("name")) for q in before.get("quests", []) if isinstance(q, dict)}
    new_quests = {str(q.get("name")) for q in state.get("quests", []) if isinstance(q, dict)}
    if new_quests - old_quests: changes.append("New quests: " + ", ".join(sorted(new_quests - old_quests)))
    beat = {"turn": turn, "time": state.get("world_time", ""), "canon_day": canon_day,
            "action": str(trigger or "World advance")[:300], "summary": clean_narrative, "changes": changes}
    buffer = state.setdefault("chapter_buffer", [])
    buffer.append(beat)
    state["chapter_buffer"] = buffer[-CHAPTER_BEAT_BACKSTOP:]
    buffer = state["chapter_buffer"]
    first_day = buffer[0].get("canon_day", canon_day)
    days_elapsed = canon_day - first_day
    if days_elapsed < CHAPTER_SPAN_DAYS and len(buffer) < CHAPTER_BEAT_BACKSTOP:
        return None
    chapter_number = len(state.setdefault("chapter_summaries", [])) + 1
    snippets = [entry.get("summary", "") for entry in buffer if entry.get("summary")]
    summary = " ".join(snippets)[:2400]
    chapter = {
        "number": chapter_number,
        "title": f"Chapter {chapter_number}: {state.get('location', 'A Changing World')}",
        "turns": [buffer[0].get("turn", turn), buffer[-1].get("turn", turn)],
        "time_span": f"{buffer[0].get('time', '')} — {buffer[-1].get('time', '')}",
        "summary": summary,
        "key_decisions": [entry.get("action") for entry in buffer if entry.get("action")][:12],
        "lasting_changes": [change for entry in buffer for change in entry.get("changes", [])][:20],
        "unresolved_quests": [q.get("name") for q in state.get("quests", []) if isinstance(q, dict) and str(q.get("status", "active")).lower() == "active"],
    }
    state["chapter_summaries"].append(chapter)
    state["chapter_summaries"] = state["chapter_summaries"][-60:]
    state["chapter_buffer"] = []
    return chapter


def _clock(name, kind, goal, threshold=100):
    return {"name": name, "kind": kind, "goal": goal, "progress": 0, "threshold": threshold, "status": "active",
            "last_update": "Not yet advanced", "method": "organized effort" if kind == "faction" else "personal effort",
            "target_location": "", "travel_remaining_days": 0, "dependencies": [],
            "resources": {"capacity": 50}, "resource_cost": {}}


# A nemesis clock deliberately takes much longer to reach its turning point
# than an ordinary companion/NPC clock (100) — a major canon villain's scheme
# is meant to loom over a long stretch of the campaign, not resolve in a
# handful of world-clock ticks like an ordinary recurring NPC's errand.
NEMESIS_CLOCK_THRESHOLD = 260


def tick_world_clocks(state, elapsed_minutes):
    faction_clocks = state.setdefault("faction_clocks", {})
    for name in state.get("factions", {}):
        faction_clocks.setdefault(name, _clock(name, "faction", f"Advance {name}'s current agenda"))
    npc_clocks = state.setdefault("npc_clocks", {})
    for name, memory in state.get("npc_memories", {}).items():
        if not isinstance(memory, dict): continue
        goal = memory.get("immediate_goal") or memory.get("goal") or memory.get("current_goal")
        nemesis = bool(memory.get("nemesis"))
        important = memory.get("recurring") or nemesis or str(memory.get("importance", "")).lower() in {"important", "major", "high"}
        if goal or important:
            clock = npc_clocks.setdefault(name, _clock(name, "npc", str(goal or "Pursue a private objective"),
                                                         NEMESIS_CLOCK_THRESHOLD if nemesis else 100))
            if nemesis:
                clock["nemesis"] = True
    elapsed_days = max(0.0, float(elapsed_minutes or 0) / 1440.0)
    step = max(1, min(18, int(math.ceil(1 + elapsed_days * 3))))
    propose_faction_conflicts(state, elapsed_days)
    events = []
    for clock_kind, clocks in (("faction", faction_clocks), ("npc", npc_clocks)):
        for key, clock in clocks.items():
            if not isinstance(clock, dict) or clock.get("status") not in {None, "active"}: continue
            causal_step = advance_causal_clock(state, clock.get("name") or key, clock, step, elapsed_days, clock_kind)
            clock["progress"] = min(int(clock.get("threshold", 100) or 100), int(clock.get("progress", 0) or 0) + causal_step)
            clock["last_update"] = state.get("world_time", "")
            if clock["progress"] >= int(clock.get("threshold", 100) or 100):
                clock["status"] = "turning_point"
                # clock.get("name") is set whenever _clock() creates the
                # entry, but the GM can also author npc_clocks/faction_clocks
                # directly via state_patch and isn't guaranteed to include
                # it — falling back to the dict key keeps this readable
                # ("None's agenda...") instead of silently mislabeling whose
                # agenda actually moved.
                who = clock.get("name") or key
                # A clock with a declared opponent gets resolved as a real
                # conflict below instead — this generic line is only for the
                # ordinary "nothing to mechanically resolve yet" case.
                if str(clock.get("opponent") or "").strip():
                    continue
                # Same field-preference pattern as npc_memories' goal
                # layering — a faction's immediate_goal (what it's actually
                # doing right now) is what a turning point should describe,
                # not the flat placeholder .goal every faction starts with.
                current_goal = clock.get("immediate_goal") or clock.get("goal")
                if clock.get("nemesis"):
                    events.append({"type": "world", "nemesis": True,
                                    "message": f"⚠ Word reaches you that {who}'s scheme has reached a breaking point: {current_goal}."})
                else:
                    events.append({"type": "world", "message": f"Somewhere beyond your own path, {who} has made real headway: {current_goal}."})
    events.extend(resolve_clock_conflicts(state))
    return events


def active_nemesis_threats(state):
    """Named villains whose long-running scheme (tracked the same way as a
    companion subplot, via npc_memories[name].nemesis) has just reached its
    breaking point — the GM should build toward a real confrontation for
    these soon rather than letting the moment quietly pass."""
    out = []
    for name, clock in (state.get("npc_clocks") or {}).items():
        if isinstance(clock, dict) and clock.get("nemesis") and clock.get("status") == "turning_point":
            out.append({"name": clock.get("name") or name, "goal": clock.get("goal", "")})
    return out


def _clock_power(clock):
    try:
        return max(1, min(100, int((clock or {}).get("power", 50) or 50)))
    except (TypeError, ValueError):
        return 50


def _effective_power(name, located):
    """A side's own power plus half their declared ally's power, if that
    ally exists and isn't itself already out of the fight — a lightweight
    stand-in for reinforcement without a full multi-front battle model."""
    _, clock = located.get(name, (None, None))
    if not clock:
        return 50
    base = _clock_power(clock)
    ally_name = str(clock.get("ally") or "").strip()
    if ally_name:
        _, ally_clock = located.get(ally_name, (None, None))
        if ally_clock and ally_clock.get("status") not in ("destroyed", "defeated"):
            base += _clock_power(ally_clock) // 2
    return base


# How low a side's power has to fall, after losing a resolved conflict,
# before it's treated as genuinely wiped out rather than merely weakened —
# giving clocks real permanent stakes instead of only narrative texture.
FACTION_DESTROYED_THRESHOLD = 15
NPC_DEFEATED_THRESHOLD = 15

# Chance per eligible multi-day tick that the sim proposes a background
# skirmish on its own, so faction conflict doesn't depend entirely on the
# GM remembering to declare one.
PROPOSED_CONFLICT_CHANCE = 0.12


def propose_faction_conflicts(state, elapsed_days):
    """Occasionally proposes a skirmish between two eligible, currently
    territory-holding canon factions so the world keeps moving even if the
    GM never gets around to declaring a conflict itself. Always marked
    `proposed` — resolve_clock_conflicts forces these to a stalemate rather
    than ever letting bare dice decide something as canon-significant as a
    faction's survival; only a GM-declared conflict (informed by the GM's
    actual canon knowledge) can end in a real win, loss, or destruction."""
    if elapsed_days < 1 or random.random() > PROPOSED_CONFLICT_CHANCE:
        return
    faction_clocks = state.get("faction_clocks") or {}
    holdings = {}
    for loc, detail in (state.get("location_details") or {}).items():
        if isinstance(detail, dict):
            f = detail.get("controlling_faction") or detail.get("faction")
            if f: holdings.setdefault(f, []).append(loc)
    eligible = [name for name, clock in faction_clocks.items()
                if isinstance(clock, dict) and clock.get("status") == "active"
                and not str(clock.get("opponent") or "").strip() and name in holdings]
    if len(eligible) < 2:
        return
    attacker, defender = random.sample(eligible, 2)
    clock = faction_clocks[attacker]
    clock["opponent"], clock["proposed"], clock["player_involved"] = defender, True, False
    clock["contested_location"] = random.choice(holdings[defender])
    clock["progress"] = min(clock.get("threshold", 100), int(clock.get("progress", 0) or 0) + 45)


def resolve_clock_conflicts(state):
    """Off-screen faction-vs-faction / NPC-vs-opponent conflict resolution.

    A clock that reaches its turning point with a GM-declared `opponent`
    rolls a strength-weighted contest between the two sides instead of just
    narrating a vague turning point — territory can change hands, and a side
    that loses badly enough is genuinely destroyed (a faction) or lost (an
    NPC), independent of whether the player witnessed any of it. A clock
    with no opponent (the ordinary case, and a nemesis whose real target is
    the player) is left completely untouched by this — it only ever fires
    for a conflict the GM explicitly opted into. A clock the application
    itself proposed (see propose_faction_conflicts) always ends in a
    stalemate instead, unless the GM has since flagged player_involved —
    only a GM-declared or GM-supervised conflict can end in a real outcome."""
    located = {}
    for coll_name in ("faction_clocks", "npc_clocks"):
        for name, clock in (state.get(coll_name) or {}).items():
            if isinstance(clock, dict):
                located[name] = (coll_name, clock)

    events = []
    resolved_this_tick = set()
    for coll_name in ("faction_clocks", "npc_clocks"):
        for name, clock in list((state.get(coll_name) or {}).items()):
            # Guards a mutual matchup (A's opponent is B and B's opponent is
            # A) from resolving twice in the same tick if both happened to
            # cross their threshold together — once either side has been
            # consumed as an actor or an opponent, it's settled for this tick.
            if name in resolved_this_tick:
                continue
            if not isinstance(clock, dict) or clock.get("status") != "turning_point":
                continue
            opponent_name = str(clock.get("opponent") or "").strip()
            if not opponent_name:
                continue
            resolved_this_tick.add(name)
            resolved_this_tick.add(opponent_name)
            opp_coll, opp_clock = located.get(opponent_name, (None, None))
            location = str(clock.get("contested_location") or "").strip()

            if clock.get("proposed") and not clock.get("player_involved"):
                # Pure dice never get to decide a faction's survival — a
                # sim-proposed skirmish always ends in a stalemate: both
                # sides feel it, nobody wins, nothing permanent changes.
                clock["power"] = max(1, _clock_power(clock) - 8)
                if opp_clock: opp_clock["power"] = max(1, _clock_power(opp_clock) - 8)
                clock["progress"], clock["opponent"], clock["contested_location"], clock["proposed"] = 0, "", "", False
                events.append({"type": "world", "conflict": True,
                                "message": f"⚔ {name} and {opponent_name} clash" + (f" over {location}" if location else "") + ", but neither gains lasting advantage."})
                continue

            power, opp_power = _effective_power(name, located), _effective_power(opponent_name, located)
            won = random.random() * (power + opp_power) < power
            ally_name = str(clock.get("ally") or "").strip()
            opp_ally_name = str(opp_clock.get("ally") or "").strip() if opp_clock else ""
            clock["progress"], clock["opponent"], clock["contested_location"], clock["proposed"] = 0, "", "", False
            winner_name = name if won else opponent_name
            winner_coll = coll_name if won else opp_coll
            if won:
                clock["power"], clock["status"] = min(100, _clock_power(clock) + 12), "active"
                if opp_clock: opp_clock["power"] = max(0, _clock_power(opp_clock) - 20)
                loser_name, loser_coll, loser_clock = opponent_name, opp_coll, opp_clock
                winner_ally, loser_ally = ally_name, opp_ally_name
            else:
                clock["power"] = max(0, _clock_power(clock) - 20)
                if opp_clock: opp_clock["power"] = min(100, _clock_power(opp_clock) + 12)
                loser_name, loser_coll, loser_clock = name, coll_name, clock
                winner_ally, loser_ally = opp_ally_name, ally_name
            # A contributing ally shares lightly in the outcome — reinforcing
            # troops gain a little from a win, or get bloodied in a loss.
            for reinforcer, delta in ((winner_ally, 3), (loser_ally, -5)):
                _, reinforcer_clock = located.get(reinforcer, (None, None))
                if reinforcer_clock and reinforcer_clock.get("status") not in ("destroyed", "defeated"):
                    reinforcer_clock["power"] = max(0, min(100, _clock_power(reinforcer_clock) + delta))
            if location and winner_coll == "faction_clocks":
                state.setdefault("location_details", {}).setdefault(location, {})["controlling_faction"] = winner_name
            if won:
                message = f"⚔ {name} has triumphed over {opponent_name}" + (f", seizing control of {location}." if location else ".")
            else:
                message = f"⚔ {name}'s campaign against {opponent_name} has failed." + (f" {opponent_name} holds {location}." if location else "")
            events.append({"type": "world", "conflict": True, "message": message})
            if loser_clock is not None and loser_coll is not None:
                threshold = FACTION_DESTROYED_THRESHOLD if loser_coll == "faction_clocks" else NPC_DEFEATED_THRESHOLD
                if loser_clock.get("power", 50) <= threshold and loser_clock.get("status") not in ("destroyed", "defeated"):
                    protected = _is_canon_protected(state, loser_name, loser_coll)
                    if loser_coll == "faction_clocks":
                        if protected:
                            # A canon-major power can be battered without
                            # being erased outright — an off-screen dice
                            # roll destroying Konoha or the World Government
                            # would break the setting's own premise, not
                            # just this campaign's continuity. It survives,
                            # weakened, instead of being wiped out.
                            loser_clock["power"] = max(loser_clock.get("power", 0), threshold + 1)
                            events.append({"type": "world", "conflict": True,
                                            "message": f"{loser_name} has been badly weakened by {winner_name}, but holds on."})
                        else:
                            loser_clock["status"] = "destroyed"
                            events.append({"type": "world", "conflict": True,
                                            "message": f"{loser_name} has been effectively wiped out by {winner_name}."})
                            events.extend(_collapse_faction(state, loser_name, winner_name))
                    else:
                        if protected:
                            loser_clock["power"] = max(loser_clock.get("power", 0), threshold + 1)
                            events.append({"type": "world", "conflict": True,
                                            "message": f"{loser_name} barely survives {winner_name}'s assault, badly shaken."})
                        else:
                            loser_clock["status"] = "defeated"
                            state.setdefault("npc_memories", {}).setdefault(loser_name, {})["status"] = "deceased"
                            events.append({"type": "world", "conflict": True,
                                            "message": f"{loser_name} has fallen, defeated by {winner_name}."})
    return events


def _is_canon_protected(state, name, kind):
    """A background/GM-declared conflict can weaken or displace a
    canon-major power, but shouldn't casually erase one outright. Factions
    are checked against this world's own known canon polities (the same
    WORLD_TERRITORIES already used to seed the map's starting territory
    colors) — cheap, reliable, no new authoring needed. NPCs have no
    equivalent built-in roster reliable enough to check automatically, so
    they're protected only when the GM has explicitly flagged them via
    npc_memories[name].canon_protected — a scripted-to-matter-later figure
    the GM knows about, not a guess this function can make on its own."""
    if kind == "faction_clocks":
        world = state.get("world", "")
        return name in set(WORLD_TERRITORIES.get(world, {}).values())
    memory = (state.get("npc_memories") or {}).get(name)
    return isinstance(memory, dict) and bool(memory.get("canon_protected"))


_LEADER_FATES = (("deceased", 0.25), ("captured", 0.40), ("exiled", 0.35))


def _collapse_faction(state, loser_name, winner_name):
    """A destroyed faction doesn't just lose the one contested location —
    everything else it held becomes genuinely unclaimed (a real power
    vacuum a neighboring faction can move into next) instead of frozen in
    place, and whoever led it shares in its fall rather than quietly
    continuing to exist untouched."""
    events = []
    vacated = []
    for loc, detail in (state.get("location_details") or {}).items():
        if isinstance(detail, dict) and detail.get("controlling_faction") == loser_name:
            detail["controlling_faction"] = ""
            vacated.append(loc)
    if vacated:
        events.append({"type": "world", "conflict": True,
                        "message": f"With {loser_name} gone, {', '.join(vacated)} " +
                                   ("are" if len(vacated) > 1 else "is") + " left unclaimed — ripe for another power to move in."})
    leaders = [name for name, mem in (state.get("npc_memories") or {}).items()
               if isinstance(mem, dict) and mem.get("leads_faction") == loser_name and mem.get("status") != "deceased"]
    for leader in leaders:
        roll, total = random.random(), 0.0
        fate = _LEADER_FATES[-1][0]
        for label, weight in _LEADER_FATES:
            total += weight
            if roll <= total:
                fate = label
                break
        state["npc_memories"][leader]["status"] = fate
        events.append({"type": "world", "conflict": True,
                        "message": f"{loser_name}'s leader, {leader}, has been {fate} in the collapse."})
    return events


def _chain_entries(value):
    """Sanitize a consequence-chain list (continuity.py) for display: keep
    only well-formed {event, turn, canon_day} entries, most recent first,
    capped for the journal card rather than the full stored history."""
    if not isinstance(value, list):
        return []
    out = [{"event": str(item.get("event"))[:300], "turn": item.get("turn"), "canon_day": item.get("canon_day")}
           for item in value if isinstance(item, dict) and item.get("event")]
    return list(reversed(out[-6:]))


def relationship_snapshot(state):
    rows = []
    memories = state.get("npc_memories", {})
    relationships = state.get("relationships", {})
    contacts = state.get("contacts", {})
    for name in sorted(set(memories) | set(relationships) | set(contacts)):
        contact = contacts.get(name, {}) if isinstance(contacts.get(name), dict) else {}
        # Major factions are contactable from campaign start, but a group
        # contact is not a person and should stay in the faction sections.
        if contact.get("kind") == "group" and name not in memories and name not in relationships:
            continue
        mem = memories.get(name) if isinstance(memories.get(name), dict) else {}
        raw = relationships.get(name, {})
        if isinstance(raw, dict):
            score = raw.get("score", raw.get("trust", mem.get("trust", 0)))
            label = raw.get("label", raw.get("status", mem.get("attitude", "Unknown")))
            promises = _list(raw.get("promises")) + _list(mem.get("promises"))
            debts = _list(raw.get("debts")) + _list(mem.get("debts"))
        else:
            score, label, promises, debts = raw, mem.get("attitude", "Unknown"), _list(mem.get("promises")), _list(mem.get("debts"))
        try: score = int(score or 0)
        except (TypeError, ValueError): score = 0
        rows.append({"name": name, "score": max(-100, min(100, score)), "label": str(label or "Unknown"),
                     "last_known_location": mem.get("last_known_location", "Unknown"), "knowledge": _list(mem.get("knows") or mem.get("knowledge")),
                     "promises": list(dict.fromkeys(map(str, promises)))[:20], "debts": list(dict.fromkeys(map(str, debts)))[:20],
                     "goal": mem.get("immediate_goal") or mem.get("goal") or mem.get("current_goal") or "Unknown", "contact": contacts.get(name, {}),
                     # mid_term_goal/core_ambition are optional depth beyond the
                     # single goal line every NPC already gets — only present
                     # once the GM has actually bothered laying out this NPC's
                     # longer arc, not backfilled for every minor character.
                     "mid_term_goal": mem.get("mid_term_goal") or "", "core_ambition": mem.get("core_ambition") or "",
                     "nemesis": bool(mem.get("nemesis")), "chain": _chain_entries(mem.get("chain"))})
    affiliations = []
    for aff in state.get("affiliations", []):
        if not isinstance(aff, dict) or not str(aff.get("faction", "")).strip():
            continue
        affiliations.append({
            "faction": str(aff.get("faction", "")).strip(), "rank": str(aff.get("rank", "Member") or "Member"),
            "status": str(aff.get("status", "active") or "active"), "joined": str(aff.get("joined", "")),
            "notes": str(aff.get("notes", "")),
        })
    npc_network = []
    for key, rel in (state.get("npc_relationships") or {}).items():
        if not isinstance(rel, dict):
            continue
        a, b = str(rel.get("a") or "").strip(), str(rel.get("b") or "").strip()
        if not a or not b:
            parts = str(key).split("::", 1)
            a = a or (parts[0] if parts else "")
            b = b or (parts[1] if len(parts) > 1 else "")
        if not a or not b:
            continue
        try:
            strength = max(-100, min(100, int(rel.get("strength", 0) or 0)))
        except (TypeError, ValueError):
            strength = 0
        npc_network.append({"a": a, "b": b, "type": str(rel.get("type") or "unknown"),
                             "strength": strength, "status": str(rel.get("status") or "active"),
                             "note": str(rel.get("note") or "")})
    faction_chain = state.get("faction_chain") if isinstance(state.get("faction_chain"), dict) else {}
    return {"people": rows, "factions": [{"name": name, "standing": value, "chain": _chain_entries(faction_chain.get(name))}
                                          for name, value in state.get("reputation", {}).items()],
            "affiliations": affiliations, "npc_network": npc_network}


def campaign_health(state):
    issues = []
    def add(severity, area, message, fix, repair_id=""):
        issues.append({"severity": severity, "area": area, "message": message, "suggestion": fix,
                       "repair_id": repair_id, "repairable": bool(repair_id)})
    if not state.get("quests"): add("warning", "Journey", "No active quest is giving the campaign a visible medium-term objective.", "Follow a current lead or declare a personal quest.")
    if not state.get("chapter_summaries") and int(state.get("turn", 0) or 0) >= 8: add("warning", "Memory", "No chapter summary exists for this older campaign.", "Advance once to let the chapter memory system consolidate recent turns.")
    for quest in state.get("quests", []):
        if isinstance(quest, dict) and not quest.get("objectives"): add("error", "Quest", f"{quest.get('name', 'A quest')} has no tracked objectives.", "Normalize it into a safe discovery objective.", "normalize_quests")
        if isinstance(quest, dict) and not (quest.get("next_hint") or quest.get("first_step")): add("warning", "Quest", f"{quest.get('name', 'A quest')} has no actionable next hint.", "Add a conservative investigate-the-requirements lead.", "normalize_quests")
    vague_skills = [name for name, value in state.get("skills", {}).items() if not isinstance(value, dict) or not (value.get("description") or value.get("effect"))]
    if vague_skills: add("warning", "Skills", f"{len(vague_skills)} skill descriptions are incomplete.", "Add readable placeholder descriptions without inventing mechanics.", "describe_skills")
    if state.get("continuity_ledger", {}).get("warnings"): add("error", "Continuity", "The continuity ledger contains unresolved warnings.", "Review Journal → Continuity before a long skip.")
    if not state.get("npc_memories") and int(state.get("turn", 0) or 0) >= 4: add("warning", "NPCs", "No recurring NPC memory has been established.", "Interact with named characters or pursue a social lead.")
    memory = state.get("narrative_memory") if isinstance(state.get("narrative_memory"), dict) else {}
    if int(state.get("turn", 0) or 0) >= 4 and not any(memory.get(key) for key in ("established_facts", "player_goals", "consequences")):
        add("warning", "Memory", "Long-term narrative memory has no established facts, goals, or consequences.", "Complete a meaningful turn so the memory ledger can establish campaign anchors.")
    if state.get("location") not in state.get("discovered_locations", []): add("error", "Map", "The current location is missing from discovered locations.", "Add the current location to the discovered map.", "map_current_location")
    dead = {name for name, row in (state.get("npc_memories") or {}).items() if isinstance(row, dict) and str(row.get("status", "")).lower() in {"dead", "deceased"}}
    active_dead = [ai_text(c.get("name") if isinstance(c, dict) else c) for c in state.get("companions", []) if ai_text(c.get("name") if isinstance(c, dict) else c) in dead]
    if active_dead: add("error", "Party", f"Deceased companions remain active: {', '.join(active_dead)}.", "Remove them from the active party while preserving their history.", "remove_deceased_companions")
    duplicate_rewards = 0
    for key in ("titles", "achievements"):
        labels = [ai_text(x.get("name") if isinstance(x, dict) else x).lower() for x in state.get(key, [])]
        duplicate_rewards += len([x for i, x in enumerate(labels) if x and x in labels[:i]])
    if duplicate_rewards: add("warning", "Rewards", f"{duplicate_rewards} duplicate title or achievement entries were detected.", "Remove exact duplicates while keeping the first record.", "deduplicate_rewards")
    blocked = [clock for clocks in (state.get("npc_clocks", {}), state.get("faction_clocks", {})) for clock in clocks.values() if isinstance(clock, dict) and clock.get("blocked_reason")]
    if blocked: add("warning", "World causality", f"{len(blocked)} off-screen agenda(s) are blocked by travel, resources, or prerequisites.", "Review World Clocks to see the specific causal blockers.")
    score = max(0, 100 - sum(18 if x["severity"] == "error" else 8 for x in issues))
    return {"score": score, "status": "Healthy" if score >= 85 else "Needs attention" if score >= 60 else "Unstable", "issues": issues,
            "counts": {"active_quests": len(state.get("quests", [])), "chapters": len(state.get("chapter_summaries", [])),
                       "npc_clocks": len(state.get("npc_clocks", {})), "faction_clocks": len(state.get("faction_clocks", {})),
                       "continuity_warnings": len(state.get("continuity_ledger", {}).get("warnings", [])),
                       "memory_records": sum(len(v) for v in memory.values() if isinstance(v, list)),
                       "knowledge_audits": len(state.get("knowledge_audit", [])),
                       "causal_records": len(state.get("causality_ledger", [])),
                       "repairs": len(state.get("health_repairs", []))}}


def tension_level(state):
    """A lightweight, always-available read on how dangerous the player's
    current situation is — synthesized entirely from signals the game
    already tracks (HP, active combat, an imminent promised confrontation,
    the Tower's floor countdown where it applies). This is a UI aid only,
    never written back into narrative canon or shown to the GM as fact."""
    try:
        hp_max = max(1.0, float(state.get("hp_max", 100) or 100))
        hp_ratio = max(0.0, min(1.0, float(state.get("hp", hp_max) or 0) / hp_max))
    except (TypeError, ValueError):
        hp_ratio = 1.0
    score = 0
    reasons = []
    if hp_ratio < 0.15: score += 55; reasons.append("critically low HP")
    elif hp_ratio < 0.35: score += 35; reasons.append("badly hurt")
    elif hp_ratio < 0.6: score += 15; reasons.append("wounded")
    if isinstance(state.get("combat"), dict) and state["combat"].get("active"):
        score += 25; reasons.append("in active combat")
    canon_day = state.get("canon_day", 0) or 0
    soonest_days = None
    for sched in state.get("scheduled_events", []) or []:
        if not isinstance(sched, dict) or sched.get("resolved") or sched.get("due_canon_day") is None:
            continue
        if str(sched.get("visibility", "confirmed")).lower() == "hidden":
            continue
        try:
            days = int(sched["due_canon_day"]) - int(canon_day)
        except (TypeError, ValueError):
            continue
        if days >= 0 and (soonest_days is None or days < soonest_days):
            soonest_days = days
    if soonest_days is not None:
        if soonest_days <= 2: score += 25; reasons.append("a promised confrontation is imminent")
        elif soonest_days <= 7: score += 12; reasons.append("a promised confrontation is approaching")
    if state.get("world") == "Solo Max-Level Newbie" and not state.get("tower_over"):
        deadline = state.get("tower_floor_deadline_day")
        if isinstance(deadline, (int, float)):
            days_left = max(0, int(deadline - canon_day))
            if days_left <= 3: score += 30; reasons.append("the floor's countdown is nearly out")
            elif days_left <= 14: score += 15; reasons.append("the floor's countdown is running low")
    if active_nemesis_threats(state):
        score += 20; reasons.append("a nemesis threat has reached a breaking point")
    score = min(100, score)
    label = "Critical" if score >= 70 else "Tense" if score >= 40 else "Uneasy" if score >= 15 else "Calm"
    return {"score": score, "label": label, "reasons": reasons}


def pacing_guidance(state):
    """Deterministic pacing nudge for the GM prompt — a thin wrapper around
    signals the game already tracks (tension_level, the canon day of the
    last major beat, chapter count) rather than a new subsystem. Returns an
    instruction string to fold into gm_rules, or "" most turns, when pacing
    looks fine and there's nothing worth saying."""
    if len(state.get("chapter_summaries") or []) < 1:
        return ""  # too early in the campaign for "pacing" to mean anything yet
    last_beat_day = state.get("last_major_beat_day")
    if not isinstance(last_beat_day, (int, float)):
        return ""
    days_since_beat = int(state.get("canon_day", 0) or 0) - int(last_beat_day)
    label = tension_level(state)["label"]
    if days_since_beat >= 10 and label in ("Calm", "Uneasy"):
        return (f"\n- PACING: it has been {days_since_beat} in-story days since the last major turning point, and the "
                "situation currently reads as low-stakes. Proactively introduce a concrete complication, opportunity, or "
                "piece of rising pressure this turn rather than continuing routine, low-stakes narration — the player "
                "should rarely go this long without something new to engage with.")
    if days_since_beat <= 1 and label in ("Tense", "Critical"):
        return ("\n- PACING: multiple major beats have landed in very quick succession. Ease off for this turn or the "
                "next — let the player process, recover, and act on what just happened before introducing the next "
                "major pressure or event.")
    return ""


# Shops are only loosely specified in the GM prompt ("populate shops with
# name/type and plausible inventory/prices") — there's no strict schema, so
# an inventory item might be a {name, price} dict, use "item"/"cost"/"value"
# instead, or even just be a free-text string. This has to tolerate all of
# that rather than assume one shape.
_PRICE_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def parse_price(value):
    """Pull a plausible non-negative integer price out of a loosely-typed
    shop item field — a raw number, or free text like '50 Berries' or
    'Price: 1,200'. Returns None when nothing usable is present."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        match = _PRICE_NUMBER_RE.search(value.replace(",", ""))
        if match:
            try:
                return max(0, int(float(match.group(0))))
            except ValueError:
                return None
    return None


def _shop_item_name(item):
    if isinstance(item, dict):
        return str(item.get("name") or item.get("item") or "").strip()
    return str(item).strip()


def _shop_item_price(item):
    if isinstance(item, dict):
        for key in ("price", "cost", "value"):
            if key in item:
                price = parse_price(item[key])
                if price is not None:
                    return price
        return None
    return parse_price(item)


def resolve_shop_purchase(state, shop_name, item_name):
    """Deterministic buy: once a shop item has a real price, the arithmetic
    of paying for it doesn't need an AI turn at all — this mutates state
    in place and never touches the model, so there's no way for it to
    produce the narrated-but-not-patched currency drift the continuity
    detector (continuity.py) otherwise exists to catch after the fact.
    Returns (ok, message, price_paid_or_None)."""
    if state.get("world") == "Bleach" or (isinstance(state.get("currency"), dict) and state["currency"].get("tracked") is False):
        return False, "Bleach equipment is obtained through access, authorization, favors, requisitions, or story events—not a tracked money balance.", None
    shops = state.get("shops") if isinstance(state.get("shops"), list) else []
    shop = next((sh for sh in shops if isinstance(sh, dict)
                 and str(sh.get("name", "")).strip().lower() == str(shop_name or "").strip().lower()), None)
    if not shop:
        return False, f"No shop named '{shop_name}' is known here.", None
    inventory = shop.get("inventory") if isinstance(shop.get("inventory"), list) else (
        shop.get("items") if isinstance(shop.get("items"), list) else [])
    item = next((it for it in inventory if _shop_item_name(it).strip().lower() == str(item_name or "").strip().lower()), None)
    if item is None:
        return False, f"'{item_name}' isn't in {shop.get('name', shop_name)}'s current inventory.", None
    price = _shop_item_price(item)
    if price is None:
        return False, f"'{item_name}' doesn't have a clear price and can't be bought this way.", None
    currency = state.get("currency") if isinstance(state.get("currency"), dict) else {"name": "Currency", "amount": 0}
    amount = currency.get("amount", 0)
    if not isinstance(amount, (int, float)):
        amount = 0
    if amount < price:
        return False, f"Not enough {currency.get('name', 'currency')} — {_shop_item_name(item)} costs {price}, you have {amount}.", None
    currency["amount"] = amount - price
    state["currency"] = currency
    display_name = _shop_item_name(item)
    state.setdefault("inventory", []).append({"name": display_name, "source": f"Bought from {shop.get('name', shop_name)}"})
    if isinstance(item, dict) and isinstance(item.get("stock"), (int, float)):
        item["stock"] = item["stock"] - 1
        if item["stock"] <= 0:
            inventory.remove(item)
    return True, f"Bought {display_name} from {shop.get('name', shop_name)} for {price} {currency.get('name', 'currency')}.", price


def record_purchase_offer(state):
    """A transient, AI-facing purchase_offer ({item, price, vendor}) — set
    whenever this turn's narrative presents a concrete opportunity to buy
    something, e.g. a merchant naming a price mid-scene — becomes a
    permanent, app-owned entry in purchase_offers with a real id and
    resolved=false. Mirrors the npc_memories[name].chain_event pattern in
    continuity.py: the AI's job is just naming what's on offer, the app
    owns the durable bookkeeping (id, resolved state) so a purchase can
    never be trusted to whatever the client echoes back on click. Returns
    a small dict for the story entry's `detail` (None if nothing valid was
    offered) so the Chronicle can render a real Buy button for it."""
    raw = state.pop("purchase_offer", None)
    state["purchase_offer"] = None
    if state.get("world") == "Bleach" or (isinstance(state.get("currency"), dict) and state["currency"].get("tracked") is False):
        return None
    if not isinstance(raw, dict):
        return None
    item = str(raw.get("item") or "").strip()
    price = parse_price(raw.get("price"))
    if not item or not price:
        return None
    offer_id = secrets.token_hex(6)
    vendor = str(raw.get("vendor") or "").strip()
    offers = state.setdefault("purchase_offers", [])
    offers.append({"id": offer_id, "item": item, "price": price, "vendor": vendor, "turn": state.get("turn", 0), "resolved": False})
    state["purchase_offers"] = offers[-20:]
    currency_name = (state.get("currency") or {}).get("name", "Currency") if isinstance(state.get("currency"), dict) else "Currency"
    return {"id": offer_id, "item": item, "price": price, "vendor": vendor, "currency": currency_name}


def resolve_purchase_offer(state, offer_id):
    """Deterministic buy for a narrative purchase_offer (see
    record_purchase_offer above): looks up the REAL stored price by id —
    never trusts a client-supplied price — deducts currency, adds
    inventory, and marks the offer resolved so it can't be bought twice.
    Returns (ok, message, price_paid_or_None), same shape as
    resolve_shop_purchase."""
    if state.get("world") == "Bleach" or (isinstance(state.get("currency"), dict) and state["currency"].get("tracked") is False):
        return False, "Bleach equipment is handled through narrative access rather than a tracked money balance.", None
    offers = state.get("purchase_offers") if isinstance(state.get("purchase_offers"), list) else []
    offer = next((o for o in offers if isinstance(o, dict) and o.get("id") == offer_id), None)
    if offer is None:
        return False, "That offer is no longer available.", None
    if offer.get("resolved"):
        return False, f"You already bought {offer.get('item')}.", None
    price = offer.get("price")
    currency = state.get("currency") if isinstance(state.get("currency"), dict) else {"name": "Currency", "amount": 0}
    amount = currency.get("amount", 0)
    if not isinstance(amount, (int, float)):
        amount = 0
    if amount < price:
        return False, f"Not enough {currency.get('name', 'currency')} — {offer.get('item')} costs {price}, you have {amount}.", None
    currency["amount"] = amount - price
    state["currency"] = currency
    state.setdefault("inventory", []).append({"name": offer.get("item"), "source": f"Bought from {offer.get('vendor') or 'an offer'}"})
    offer["resolved"] = True
    return True, f"Bought {offer.get('item')} for {price} {currency.get('name', 'currency')}.", price


def _notable_individuals_for(state, place_name):
    """Best-effort cross-reference for the map's info panel: named people
    (not locations/factions/items) whose codex notes or last-known location
    mention this place. There's no dedicated location-link field in either
    structure, so this is a loose substring match, same spirit as the
    location-category matching used elsewhere."""
    place_l = str(place_name).lower()
    names = []
    for entry in state.get("codex", []):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("type", "")).lower() in ("location", "faction", "item", "region"):
            continue
        if place_l in str(entry.get("notes", "")).lower():
            name = entry.get("name")
            if name:
                names.append(str(name))
    npc_memories = state.get("npc_memories", {})
    if isinstance(npc_memories, dict):
        for name, info in npc_memories.items():
            if not isinstance(info, dict):
                continue
            loc = str(info.get("location") or info.get("last_location") or info.get("last_known_location") or "").lower()
            if loc and (place_l in loc or loc in place_l):
                names.append(str(name))
    return list(dict.fromkeys(names))


def map_snapshot(state, world_map, world):
    current = str(state.get("location", ""))
    discovered = set(state.get("discovered_locations", []))
    territories = WORLD_TERRITORIES.get(world, {})
    # Original locations the story itself introduced (a new village, a hidden
    # camp, a ruin nobody canon ever named) — the AI places these with its
    # own x/y on request; skip any that collide by name with a fixed map
    # entry rather than let a custom one silently shadow a canon location.
    fixed_names = {str(n[0]).lower() for n in world_map}
    custom_nodes = []
    for entry in state.get("custom_locations", []) or []:
        if not isinstance(entry, dict): continue
        name = str(entry.get("name") or "").strip()
        if not name or name.lower() in fixed_names: continue
        try:
            x, y = float(entry.get("x", 50)), float(entry.get("y", 50))
        except (TypeError, ValueError):
            x, y = 50.0, 50.0
        custom_nodes.append((name, x, y, str(entry.get("kind") or "landmark"), int(entry.get("tier", 1) or 1)))
    full_map = list(world_map) + custom_nodes
    current_node = next((node for node in full_map if str(node[0]).lower() in current.lower() or current.lower() in str(node[0]).lower()), full_map[0] if full_map else (current, 50, 50, "region", 1))
    quest_locations = {}
    for quest in state.get("quests", []):
        if not isinstance(quest, dict): continue
        for location in _list(quest.get("locations")):
            quest_locations.setdefault(str(location).lower(), []).append(quest.get("name", "Quest"))
    scale = progression_preset_for(world).get("travel_scale", 1.0)
    current_turn = int(state.get("turn", 0) or 0)
    nodes = []
    for name, x, y, kind, tier in full_map:
        distance = math.dist((float(current_node[1]), float(current_node[2])), (float(x), float(y)))
        travel_minutes = 0 if name == current_node[0] else max(30, int(round(distance * 38 * scale + max(0, int(tier or 1) - 1) * 12)))
        quests = []
        for loc, names in quest_locations.items():
            if loc in str(name).lower() or str(name).lower() in loc: quests.extend(names)
        detail = state.get("location_details", {}).get(name, {}) if isinstance(state.get("location_details", {}).get(name), dict) else {}
        changed_turn = detail.get("controller_changed_turn")
        # A window, not a one-shot flag, so the highlight survives across a
        # couple of turns of the player just not happening to open the map
        # the instant it changed — see update_continuity's territory diff.
        recently_changed = isinstance(changed_turn, (int, float)) and (current_turn - int(changed_turn)) <= 3
        nodes.append({"name": name, "x": x, "y": y, "kind": kind, "tier": tier, "current": name == current_node[0],
                      "discovered": name in discovered or name == current_node[0], "travel_minutes": travel_minutes,
                      "controller": detail.get("controlling_faction") or detail.get("faction") or territories.get(name, "Unknown"),
                      "quests": list(dict.fromkeys(quests)), "notes": detail.get("notes") or detail.get("description") or "No additional local notes recorded.",
                      "notable_individuals": _notable_individuals_for(state, name), "danger_level": str(detail.get("danger_level") or ""),
                      "recently_changed": recently_changed})
    return {"nodes": nodes}
