"""Deterministic campaign subsystems used around AI-authored narration.

These helpers keep long-campaign memory, world clocks, quest structure,
progression tuning, map planning, and health diagnostics stable even when a
smaller narrator model omits optional bookkeeping.
"""
import copy
import math
import re

from util import ai_text

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
    "Custom World": {"label": "Setting-defined growth", "training_rate": 1.00, "breakthrough_rate": 1.00, "xp_rate": 1.00, "travel_scale": 1.00},
}


WORLD_TERRITORIES = {
    "One Piece": {"Shells Town": "Marines", "Loguetown": "Marines", "Enies Lobby": "World Government", "Sabaody": "World Government", "Arlong Park": "Pirates"},
    "Hunter x Hunter": {"Hunter Exam Site": "Hunter Association", "Hunter Association HQ": "Hunter Association", "Meteor City": "Phantom Troupe", "Kukuroo Mountain": "Zoldyck Family", "Yorknew City": "Yorknew Mafia"},
    "Naruto": {"Konohagakure": "Konohagakure", "Sunagakure": "Sunagakure", "Kirigakure": "Kirigakure", "Kumogakure": "Kumogakure", "Iwagakure": "Iwagakure"},
    "Solo Max-Level Newbie": {"Earth — Tower Entrance": "Players", "Floor 10": "Tower Administrators", "Floor 20": "Tower Administrators", "Floor 30": "Tower Administrators", "Floor 40": "Tower Administrators", "Floor 50+": "Tower Administrators"},
    "Overgeared": {"Winston": "Local Lords", "Titan": "Kingdom", "Saharan Empire": "Kingdom", "Reidan": "Guilds"},
    "Reincarnated as a Slime": {"Great Jura Forest": "Jura Forest Monsters", "Goblin Village": "Jura Forest Monsters", "Tempest": "Jura Forest Monsters", "Kingdom of Falmuth": "Kingdom of Falmuth", "Demon Lord's Domain": "Demon Lords"},
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
        quest.setdefault("branch_state", {"current": "main", "available": [], "locked": []})
        quest.setdefault("consequences", [])
        required = [obj for obj in objectives if not obj.get("optional")]
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


def _clock(name, kind, goal):
    return {"name": name, "kind": kind, "goal": goal, "progress": 0, "threshold": 100, "status": "active", "last_update": "Not yet advanced"}


def tick_world_clocks(state, elapsed_minutes):
    faction_clocks = state.setdefault("faction_clocks", {})
    for name in state.get("factions", {}):
        faction_clocks.setdefault(name, _clock(name, "faction", f"Advance {name}'s current agenda"))
    npc_clocks = state.setdefault("npc_clocks", {})
    for name, memory in state.get("npc_memories", {}).items():
        if not isinstance(memory, dict): continue
        goal = memory.get("goal") or memory.get("current_goal")
        important = memory.get("recurring") or str(memory.get("importance", "")).lower() in {"important", "major", "high"}
        if goal or important:
            npc_clocks.setdefault(name, _clock(name, "npc", str(goal or "Pursue a private objective")))
    elapsed_days = max(0.0, float(elapsed_minutes or 0) / 1440.0)
    step = max(1, min(18, int(math.ceil(1 + elapsed_days * 3))))
    events = []
    for clocks in (faction_clocks, npc_clocks):
        for clock in clocks.values():
            if not isinstance(clock, dict) or clock.get("status") not in {None, "active"}: continue
            clock["progress"] = min(int(clock.get("threshold", 100) or 100), int(clock.get("progress", 0) or 0) + step)
            clock["last_update"] = state.get("world_time", "")
            if clock["progress"] >= int(clock.get("threshold", 100) or 100):
                clock["status"] = "turning_point"
                events.append({"type": "world", "message": f"{clock.get('name')}'s agenda reached a turning point: {clock.get('goal')}."})
    return events


def relationship_snapshot(state):
    rows = []
    memories = state.get("npc_memories", {})
    relationships = state.get("relationships", {})
    contacts = state.get("contacts", {})
    for name in sorted(set(memories) | set(relationships) | set(contacts)):
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
                     "goal": mem.get("goal") or mem.get("current_goal") or "Unknown", "contact": contacts.get(name, {})})
    affiliations = []
    for aff in state.get("affiliations", []):
        if not isinstance(aff, dict) or not str(aff.get("faction", "")).strip():
            continue
        affiliations.append({
            "faction": str(aff.get("faction", "")).strip(), "rank": str(aff.get("rank", "Member") or "Member"),
            "status": str(aff.get("status", "active") or "active"), "joined": str(aff.get("joined", "")),
            "notes": str(aff.get("notes", "")),
        })
    return {"people": rows, "factions": [{"name": name, "standing": value} for name, value in state.get("reputation", {}).items()],
            "affiliations": affiliations}


def campaign_health(state):
    issues = []
    def add(severity, area, message, fix): issues.append({"severity": severity, "area": area, "message": message, "suggestion": fix})
    if not state.get("quests"): add("warning", "Journey", "No active quest is giving the campaign a visible medium-term objective.", "Follow a current lead or declare a personal quest.")
    if not state.get("chapter_summaries") and int(state.get("turn", 0) or 0) >= 8: add("warning", "Memory", "No chapter summary exists for this older campaign.", "Advance once to let the chapter memory system consolidate recent turns.")
    for quest in state.get("quests", []):
        if isinstance(quest, dict) and not quest.get("objectives"): add("error", "Quest", f"{quest.get('name', 'A quest')} has no tracked objectives.", "Open or advance the quest so its state can be normalized.")
    vague_skills = [name for name, value in state.get("skills", {}).items() if not isinstance(value, dict) or not (value.get("description") or value.get("effect"))]
    if vague_skills: add("warning", "Skills", f"{len(vague_skills)} skill descriptions are incomplete.", "Use or investigate those skills so the GM can establish effects and limits.")
    if state.get("continuity_ledger", {}).get("warnings"): add("error", "Continuity", "The continuity ledger contains unresolved warnings.", "Review Journal → Continuity before a long skip.")
    if not state.get("npc_memories") and int(state.get("turn", 0) or 0) >= 4: add("warning", "NPCs", "No recurring NPC memory has been established.", "Interact with named characters or pursue a social lead.")
    if state.get("location") not in state.get("discovered_locations", []): add("error", "Map", "The current location is missing from discovered locations.", "The next state repair will add it automatically.")
    score = max(0, 100 - sum(18 if x["severity"] == "error" else 8 for x in issues))
    return {"score": score, "status": "Healthy" if score >= 85 else "Needs attention" if score >= 60 else "Unstable", "issues": issues,
            "counts": {"active_quests": len(state.get("quests", [])), "chapters": len(state.get("chapter_summaries", [])),
                       "npc_clocks": len(state.get("npc_clocks", {})), "faction_clocks": len(state.get("faction_clocks", {})),
                       "continuity_warnings": len(state.get("continuity_ledger", {}).get("warnings", []))}}


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
    current_node = next((node for node in world_map if str(node[0]).lower() in current.lower() or current.lower() in str(node[0]).lower()), world_map[0] if world_map else (current, 50, 50, "region", 1))
    quest_locations = {}
    for quest in state.get("quests", []):
        if not isinstance(quest, dict): continue
        for location in _list(quest.get("locations")):
            quest_locations.setdefault(str(location).lower(), []).append(quest.get("name", "Quest"))
    scale = progression_preset_for(world).get("travel_scale", 1.0)
    nodes = []
    for name, x, y, kind, tier in world_map:
        distance = math.dist((float(current_node[1]), float(current_node[2])), (float(x), float(y)))
        travel_minutes = 0 if name == current_node[0] else max(30, int(round(distance * 38 * scale + max(0, int(tier or 1) - 1) * 12)))
        quests = []
        for loc, names in quest_locations.items():
            if loc in str(name).lower() or str(name).lower() in loc: quests.extend(names)
        detail = state.get("location_details", {}).get(name, {}) if isinstance(state.get("location_details", {}).get(name), dict) else {}
        nodes.append({"name": name, "x": x, "y": y, "kind": kind, "tier": tier, "current": name == current_node[0],
                      "discovered": name in discovered or name == current_node[0], "travel_minutes": travel_minutes,
                      "controller": detail.get("controlling_faction") or detail.get("faction") or territories.get(name, "Unknown"),
                      "quests": list(dict.fromkeys(quests)), "notes": detail.get("notes") or detail.get("description") or "No additional local notes recorded.",
                      "notable_individuals": _notable_individuals_for(state, name)})
    return {"nodes": nodes}
