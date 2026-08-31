"""Persistent world-native membership, command chains and NPC life histories.

Membership is independent of scene presence. Changes arrive through narrative
events; the roster is a view, not a strategy-game management menu.
"""
import copy
import math
import re
from gm_refinements import obj, seq, fingerprint
from age_system import numeric_age
from power_benchmarks import benchmark_tier
from worlds import power_profile_for, abilities_for

ACTIVE = {"active", "away", "missing"}
FORMER = {"left", "retired", "dead", "deceased", "expelled"}
LABELS = {
    "One Piece": "Pirate Crew", "Naruto": "Ninja Squad", "Bleach": "Division",
    "Hunter x Hunter": "Hunter Team", "Jujutsu Kaisen": "Sorcerer Team",
    "Overgeared": "Guild", "Solo Max-Level Newbie": "Raid Party",
    "Reincarnated as a Slime": "Nation & Retainers", "Custom World": "Company",
}


def text(value):
    return str(value or "").strip()


def number(value, default=0):
    try:
        n = float(value)
        return n if math.isfinite(n) else default
    except (ValueError, TypeError):
        return default


def campaign_day(state):
    minute = state.get("canon_time_minutes")
    if isinstance(minute, (int, float)) and math.floor(minute / 1440) == number(state.get("canon_day")):
        return minute / 1440
    return number(state.get("canon_day"))


def label_for(world, name="", kind=""):
    blob = f"{kind} {name}".casefold()
    if world == "One Piece":
        if re.search(r"marine|navy", blob): return "Marine Squad"
        if re.search(r"revolution", blob): return "Revolutionary Unit"
    if world == "Naruto" and re.search(r"organization|organisation|\borg\b|akatsuki|root|anbu|village|gakure|konoha", blob): return "Shinobi Organization"
    if world == "Bleach":
        if re.search(r"quincy|wandenreich", blob): return "Quincy Unit"
        if re.search(r"arrancar|espada|hollow", blob): return "Arrancar Faction"
        if re.search(r"academy|student", blob): return "Academy Cohort"
    if world == "Hunter x Hunter":
        if "troupe" in blob: return "Phantom Troupe"
        if "expedition" in blob: return "Expedition Team"
    if world == "Jujutsu Kaisen":
        if "clan" in blob: return "Great Clan"
        if "curse" in blob and "user" in blob: return "Curse-User Group"
        if "spirit" in blob: return "Curse Alliance"
    if world == "Solo Max-Level Newbie" and "guild" in blob: return "Guild"
    return LABELS.get(world, "Company")


def known_people(state):
    people = {name: dict(obj(row)) for name, row in obj(state.get("npc_memories")).items()}
    for row in seq(state.get("companions")):
        if isinstance(row, str): row = {"name": row}
        if isinstance(row, dict) and text(row.get("name")):
            name = text(row["name"])
            name = next((n for n in people if n.casefold() == name.casefold()), name)
            people[name] = {**row, **obj(people.get(name))}
    return people


def membership_copy(state):
    """Views must not copy the campaign's growing Chronicle and image caches."""
    local = dict(state)
    for key in ("organizations", "organization_lives"):
        local[key] = copy.deepcopy(obj(state.get(key)))
    return local


def group_id(name):
    return fingerprint(text(name).casefold())[:16]


def member_status(row):
    status = text(row.get("membership_status") or row.get("status")).casefold()
    status = {"former": "left", "exiled": "expelled", "invited": "candidate"}.get(status, status)
    if row.get("alive") is False: return "dead"
    return status if status in ACTIVE | FORMER | {"candidate"} else "active"


def ensure_organizations(state):
    """Add legacy memberships once; omissions/proximity never remove members."""
    groups = state.get("organizations")
    if not isinstance(groups, dict): groups = state["organizations"] = {}
    for gid, group in list(groups.items()):
        if not isinstance(group, dict):
            groups.pop(gid)
            continue
        group.setdefault("id", gid)
        group.setdefault("name", "Unnamed group")
        group["members"] = {text(n): row for n, row in obj(group.get("members")).items() if text(n) and isinstance(row, dict)}
        group["history"] = seq(group.get("history"))
    player = text(state.get("name"))
    people = known_people(state)
    canon_people = None
    discovered = {}
    for raw in seq(state.get("affiliations")):
        row = raw if isinstance(raw, dict) else {"name": raw}
        name = text(row.get("name") or row.get("faction") or row.get("organization"))
        if name and member_status(row) in ACTIVE:
            discovered[name] = row
    for name, roster in obj(state.get("faction_rosters")).items():
        names = [text(r.get("name") if isinstance(r, dict) else r) for r in seq(roster)]
        if player and player.casefold() in [n.casefold() for n in names]: discovered.setdefault(name, {})
    for raw in seq(state.get("companions")):
        if isinstance(raw, dict):
            name = text(raw.get("group") or raw.get("organization"))
            if name: discovered.setdefault(name, {})
    if not discovered and seq(state.get("companions")) and not groups:
        discovered["Unnamed group"] = {"provisional": True}
    for name, info in discovered.items():
        gid = group_id(name)
        initial_membership = gid not in groups
        group = groups.setdefault(gid, {"id": gid, "name": name, "members": {}, "history": [], "leader": "",
                                        "kind": info.get("kind", ""), "provisional": bool(info.get("provisional"))})
        members = group.setdefault("members", {})
        if not isinstance(members, dict): members = group["members"] = {}
        roster = seq(obj(state.get("faction_rosters")).get(name))
        candidates = [r if isinstance(r, dict) else {"name": r} for r in roster]
        if player: candidates.insert(0, {"name": player, "position": info.get("rank") or info.get("role") or state.get("position") or "Member"})
        for raw in seq(state.get("companions")):
            row = raw if isinstance(raw, dict) else {"name": raw}
            assigned = text(row.get("group") or row.get("organization"))
            if assigned == name or (not assigned and len(discovered) == 1): candidates.append(row)
        for candidate in candidates:
            member_name = text(candidate.get("name"))
            if not member_name: continue
            member_name = next((n for n in members if n.casefold() == member_name.casefold()), member_name)
            if member_name not in members and not initial_membership: continue
            if member_name not in members and canon_people is None:
                from canon_integrity import active_canon_identities
                canon_people = {text(alias).casefold(): record for record in active_canon_identities(state.get("world"), state)
                                for alias in [record.get("name"), *seq(record.get("aliases"))] if text(alias)}
            memory = {**obj(obj(canon_people).get(member_name.casefold())), **obj(people.get(member_name)), **candidate}
            if member_name not in members:
                members[member_name] = {"name": member_name, "position": text(memory.get("position") or memory.get("rank") or memory.get("role")) or "Member",
                    "status": member_status(memory), "joined_day": campaign_day(state), "reports_to": text(memory.get("reports_to") or memory.get("commander")),
                    "unit": text(memory.get("unit") or memory.get("squad")), "membership_basis": "Recorded campaign membership"}
                for key in ("independent", "motivation", "terms", "commitments", "loyalty_basis"):
                    if key in memory: members[member_name][key] = copy.deepcopy(memory[key])
                if memory.get("subordinate") is True and not members[member_name]["reports_to"]:
                    members[member_name]["reports_to"] = player
            # Current facts can mark a member absent/dead, but stale roster rows
            # must never resurrect a former member or undo an explicit departure.
            current_status = member_status(obj(people.get(member_name)))
            if current_status in FORMER: members[member_name]["status"] = current_status
            if not group.get("leader") and re.fullmatch(r"captain|leader|guild master|commander|founder|ruler", members[member_name]["position"], re.I):
                group["leader"] = member_name
    # Apply current known deaths even to groups no longer in the nearby party.
    for group in groups.values():
        if not isinstance(group, dict): continue
        for name, member in obj(group.get("members")).items():
            if not isinstance(member, dict): continue
            memory = obj(people.get(name))
            if memory and member_status(memory) in FORMER: member["status"] = member_status(memory)
            if name == player and state.get("alive") is False: member["status"] = "dead"
    state["organization_lives"] = {text(n): row for n, row in obj(state.get("organization_lives")).items() if isinstance(row, dict)}
    return groups


def command_chain(group, name, player):
    members = obj(group.get("members")); path = []; seen = set()
    while name and name not in seen and name in members:
        seen.add(name)
        row = obj(members[name])
        if row.get("status") not in ACTIVE or row.get("status") == "missing": return []
        if row.get("independent") is True: return []
        if name == player: return list(reversed(path))
        path.append(name)
        parent = text(row.get("reports_to")) or text(group.get("leader"))
        name = player if parent in {"player", "the player"} else parent
    return []


def organization_commands(state, query):
    if not re.search(r"\b(order|command|instruct|tell|direct|assign|have|ask)\b", query, re.I): return []
    groups = ensure_organizations(state); player = text(state.get("name")); result = []
    recent = obj(state.get("last_command_context"))
    referents = seq(recent.get("actors")) if 0 <= number(state.get("turn"))-number(recent.get("turn"), -100) <= 2 else []
    if not re.search(r"\bthem\b", query, re.I) and len(referents) != 1: referents = []
    followup = bool(re.search(r"\b(?:her|him|them)\b", query, re.I))
    explicit_names = {name for group in groups.values() for name in obj(group.get("members"))
                      if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", query, re.I)}
    for group in groups.values():
        if not isinstance(group, dict): continue
        label = label_for(state.get("world"), group.get("name", ""), group.get("kind", ""))
        generic = re.search(r"\bmy (crew|squad|organization|guild|retainers|team)\b", query, re.I)
        whole = text(group.get("name")).casefold() in query.casefold() or bool(generic and (generic[1].casefold() in label.casefold() or len(groups) == 1))
        for name, member in obj(group.get("members")).items():
            if not isinstance(member, dict) or name == player: continue
            unit = text(member.get("unit"))
            selected = whole or name in explicit_names or (unit and unit.casefold() in query.casefold()) or (followup and not explicit_names and name in referents)
            if not selected: continue
            chain = command_chain(group, name, player)
            if not chain: continue
            result.append({"actor": name, "order": query[:900], "group": group["name"], "group_type": label,
                "via": chain[:-1], "basis": "established organizational command chain",
                "default": "Preserve the objective, constraints and duration through this command chain; use real communication, not telepathy.",
                "exceptions": "Only established inability, conflicting duty, or ambiguity; ordinary disagreement does not replace the command."})
    return result


def power_for(state, name, member=None, people=None):
    world = state.get("world", "Custom World")
    player = name == state.get("name")
    memory = state if player else obj((people if people is not None else known_people(state)).get(name))
    if not player and (memory.get("power_hidden") or memory.get("power_known") is False):
        return {"label": "Not assessed", "score": None, "source": "Hidden or unobserved capability", "estimated": True}
    stats = obj(memory.get("stats"))
    score = None; source = ""; estimated = not player
    if any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in stats.values()):
        profile = power_profile_for(world, stats, memory.get("archetype", ""))
        score = obj(profile.get("world_combat") or profile.get("combat")).get("score")
        source = "Character sheet" if player else "Recorded combat attributes"; estimated = False
    elif isinstance(memory.get("power_score"), (int, float)):
        score = number(memory["power_score"]); source = "Campaign estimate"
    if score is None:
        from engine_social import _role_power_estimate, LOCAL_CANON_POWER_ESTIMATES
        from canon_integrity import active_canon_identities
        role = " ".join(text(memory.get(k)) for k in ("rank", "role", "combat_tier"))
        score = _role_power_estimate(world, role); source = "Recorded role estimate"
        if score is None:
            for record in active_canon_identities(world, state):
                aliases = [record.get("name"), *seq(record.get("aliases"))]
                if name.casefold() in [text(a).casefold() for a in aliases]:
                    score = _role_power_estimate(world, " ".join(text(record.get(k)) for k in ("role", "rank", "position")))
                    source = "Current-era canon role estimate"; break
            if score is None:
                candidates = [(alias, value) for alias, value in LOCAL_CANON_POWER_ESTIMATES.get(world, {}).items()
                              if alias.casefold() == name.casefold()]
                if candidates:
                    score = max(candidates, key=lambda pair: len(pair[0]))[1]; source = "Canon baseline estimate"
    if score is None:
        return {"label": "Not assessed", "score": None, "source": "No observed combat benchmark yet", "estimated": True}
    tier = benchmark_tier(world, score)
    return {"label": tier["name"], "score": tier["score"], "source": source, "estimated": estimated}


def history(group, state, event, name, reason):
    row = {"turn": state.get("turn", 0), "day": state.get("canon_day"), "event": event, "name": name, "reason": reason}
    rows = group.setdefault("history", [])
    if row not in rows: rows.append(row)
    group["history"] = rows[-160:]


def sync_memberships(state, groups):
    """One source for organizational roles; keep legacy prompt fields consistent."""
    state["faction_rosters"] = obj(state.get("faction_rosters"))
    for group in groups.values():
        if group.get("provisional"): continue
        members = obj(group.get("members"))
        state["faction_rosters"][group["name"]] = [name for name, row in members.items() if obj(row).get("status") in ACTIVE]
        player = obj(members.get(text(state.get("name"))))
        if not player: continue
        affiliations = seq(state.get("affiliations"))
        affiliation = next((r for r in affiliations if isinstance(r, dict) and text(r.get("faction") or r.get("name")).casefold() == group["name"].casefold()), None)
        if affiliation is None:
            affiliation = {"faction": group["name"]}; affiliations.append(affiliation)
        affiliation.update(rank=player.get("position", "Member"), status="active" if player.get("status") in ACTIVE else "former")
        state["affiliations"] = affiliations


def organization_issues(state, data):
    if not seq(data.get("organization_updates")): return []
    groups = ensure_organizations(membership_copy(state)); issues = []
    for event in seq(data.get("organization_updates")):
        if not isinstance(event, dict): continue
        if not text(event.get("reason")): issues.append("Organizational changes require an established narrative reason.")
        action = event.get("event")
        group = groups.get(group_id(event.get("group", "")), {})
        if action == "join" and event.get("accepted") is not True:
            issues.append("Joining requires agreement; an invitation alone creates a candidate, not a member.")
        if action == "succession_plan" and event.get("accepted") is not True:
            issues.append("A successor must accept before a succession plan takes effect.")
        if action == "succession_plan" and text(event.get("name")) not in obj(group.get("members")):
            issues.append("Choose an established member as successor; do not invent a replacement.")
        if action == "retire" and event.get("name") == state.get("name") and event.get("accepted") is not True:
            issues.append("The player's retirement must be explicitly voluntary and accepted, never automatic.")
        if action == "development" and not text(event.get("activity")):
            issues.append("NPC development needs a concrete ongoing activity, not player-level scaling.")
        if action == "development" and event.get("rate") == "exceptional" and not text(event.get("method")):
            issues.append("Exceptional NPC growth requires an established accelerated method.")
    return issues


def apply_updates(state, data, interval_start=None):
    groups = ensure_organizations(state)
    for event in seq(data.get("organization_updates"))[:100]:
        if not isinstance(event, dict) or not text(event.get("reason")): continue
        group_name = text(event.get("group")); gid = group_id(group_name); action = event.get("event")
        if not group_name: continue
        if action == "establish":
            if gid not in groups:
                groups[gid] = {"id": gid, "name": group_name, "kind": text(event.get("kind")), "leader": text(event.get("leader")), "members": {}, "history": []}
                groups[gid]["members"][text(state.get("name"))] = {"name": state.get("name"), "position": text(event.get("position")) or ("Leader" if event.get("leader") == state.get("name") else "Member"), "status": "active", "joined_day": state.get("canon_day", 0)}
            history(groups[gid], state, action, state.get("name"), event["reason"])
            continue
        group = groups.get(gid)
        if not isinstance(group, dict): continue
        name = text(event.get("name")); members = group.setdefault("members", {})
        name = next((n for n in members if n.casefold() == name.casefold()), name)
        if not name: continue
        row = obj(members.get(name))
        if action in {"invite", "join", "birth"}:
            if action == "join" and event.get("accepted") is not True: continue
            if action == "invite" and row.get("status") in ACTIVE: continue
            # A dead member never returns through a routine recruitment event.
            if row.get("status") in {"dead", "deceased"}: continue
            row = members.setdefault(name, {"name": name, "joined_day": state.get("canon_day", 0)})
            row.update(status="candidate" if action == "invite" else "active",
                       position=text(event.get("position")) or ("Dependent" if action == "birth" else row.get("position", "Member")),
                       membership_basis=text(event["reason"]))
            memories = state.setdefault("npc_memories", {})
            if not isinstance(memories.get(name), dict): memories[name] = {}
            memory = memories[name]
            if action == "birth":
                if name in state["organization_lives"] and state["organization_lives"][name].get("birth_recorded"): continue
                memory["age"] = 0
                life = state["organization_lives"].setdefault(name, {})
                life.update(age_anchor_day=number(state.get("canon_day")), age_anchor_value=0, stage="child", birth_recorded=True)
                for key in ("parents", "aging_mode"):
                    if key in event: life[key] = copy.deepcopy(event[key])
        elif not row: continue
        elif action in {"leave", "retire", "expel", "death", "away", "return"}:
            if action == "retire" and name == state.get("name") and event.get("accepted") is not True: continue
            if row.get("status") in {"dead", "deceased"}: continue
            if action == "return" and row.get("status") not in {"away", "missing"}: continue
            row["status"] = {"leave": "left", "retire": "retired", "expel": "expelled", "death": "dead", "away": "away", "return": "active"}[action]
            if row["status"] in FORMER:
                row["departure_reason"] = event["reason"]
                # Membership ends here, not every independent relationship.
                state["companions"] = [c for c in seq(state.get("companions")) if text(c.get("name") if isinstance(c, dict) else c).casefold() != name.casefold()]
            if action == "death":
                memories = state.setdefault("npc_memories", {})
                memories[name] = {**obj(memories.get(name)), "alive": False, "status": "dead"}
        elif action == "position":
            row["position"] = text(event.get("position")) or row.get("position", "Member")
        elif action == "succession_plan":
            if event.get("accepted") is not True or row.get("status") not in ACTIVE: continue
            group["succession"] = {"successor": name, "accepted": True, "trigger": "leader death or explicit retirement", "reason": event["reason"]}
        elif action == "development":
            if not text(event.get("activity")): continue
            life = state["organization_lives"].setdefault(name, {})
            life["development"] = {k: copy.deepcopy(event[k]) for k in ("activity", "discipline", "mentor", "rate", "method", "active") if k in event}
            life["development"]["started_day"] = number(interval_start, number(state.get("canon_day")))
        elif action == "life":
            life = state["organization_lives"].setdefault(name, {})
            for key in ("parents", "mentor", "stage", "aging_mode", "maturity_age"):
                if key in event: life[key] = copy.deepcopy(event[key])
        else: continue
        for key in ("reports_to", "unit", "independent", "motivation", "terms", "commitments", "loyalty_basis"):
            if key in event: row[key] = copy.deepcopy(event[key])
        if action in {"position", "join"} and event.get("leader") == name:
            group["leader"] = name
        history(group, state, action, name, event["reason"])
    # The legacy membership field remains useful to existing GM/map systems.
    sync_memberships(state, groups)


def advance_lives(state, elapsed_minutes, before=None):
    groups = ensure_organizations(state); people = known_people(state)
    end = campaign_day(state); elapsed_days = max(0, number(elapsed_minutes) / 1440)
    lives = state["organization_lives"]; notices = []
    members = {}
    for group in groups.values():
        for name, row in obj(group.get("members")).items():
            if name not in members or row.get("status") in ACTIVE: members[name] = row
    for name, member in members.items():
        if name == state.get("name") or member.get("status") in {"candidate", "dead", "deceased"}: continue
        memories = state.setdefault("npc_memories", {})
        if not isinstance(memories.get(name), dict): memories[name] = dict(obj(people.get(name)))
        memory = memories[name]
        for key in ("age", "stats", "power_score", "training", "goal", "condition"):
            if key not in memory and key in obj(people.get(name)): memory[key] = copy.deepcopy(people[name][key])
        life = lives.setdefault(name, {})
        start = max(number(life.get("last_day"), end-elapsed_days), end-elapsed_days, number(member.get("joined_day"), end-elapsed_days))
        days = max(0, end-start); life["last_day"] = max(end, number(life.get("last_day"), end))
        age = numeric_age(memory.get("age"))
        if age is not None:
            if "last_published_age" in life and life["last_published_age"] != age:
                life.update(age_anchor_day=end, age_anchor_value=age)
            if "age_anchor_day" not in life:
                life.update(age_anchor_day=start, age_anchor_value=age)
            chronological = int(life["age_anchor_value"]) + int(max(0, end-number(life["age_anchor_day"])) // 360)
            life["chronological_age"] = chronological
            mode = life.get("aging_mode") or memory.get("aging_mode", "mortal")
            if mode not in {"ageless", "immortal", "spiritual", "arrested"}: memory["age"] = chronological
            life["last_published_age"] = memory["age"]
            if life.get("stage") == "child" and number(life.get("maturity_age")) > 0 and memory["age"] >= number(life["maturity_age"]):
                life["stage"] = "adult"
        development = obj(life.get("development"))
        # Existing narrative training directives are also usable, without inventing a job.
        activity = text(development.get("activity")) or text(memory.get("training") or memory.get("immediate_goal") or memory.get("goal") or memory.get("current_goal"))
        if member.get("status") not in {"active", "away"} or development.get("active") is False: continue
        if not re.search(r"\b(train|practice|study|learn|research|apprentice)\w*\b", activity, re.I): continue
        if re.search(r"\b(unconscious|critical|incapacitated)\b", text(memory.get("condition")), re.I): continue
        effective_days = min(days, max(0, end-number(development.get("started_day"), start)))
        credit = number(life.get("training_days")) + effective_days
        months = int((credit + 1e-8) // 30); life["training_days"] = max(0, credit - months * 30)
        if not months: continue
        discipline = text(development.get("discipline"))
        if not discipline:
            discipline = next((key for key in abilities_for(state.get("world", "Custom World")) if key.casefold() in activity.casefold()), "")
        stat_key = next((key for key in abilities_for(state.get("world", "Custom World")) if key.casefold() == discipline.casefold()), None)
        rate = 1.5 if development.get("rate") == "focused" else 1
        if development.get("rate") == "exceptional" and text(development.get("method")): rate = 3
        if text(development.get("mentor")) in people: rate *= 1.2
        if re.search(r"injur|wound|recover", text(memory.get("condition")), re.I): rate *= .5
        gain = 0.0
        if stat_key and isinstance(obj(memory.get("stats")).get(stat_key), (int, float)):
            old = number(memory["stats"][stat_key]); value = old
            prior = obj(obj(obj(before).get("npc_memories")).get(name))
            baseline = obj(prior.get("stats")).get(stat_key)
            if isinstance(baseline, (int, float)) and 0 <= baseline <= old: value = baseline
            for _ in range(min(months, 1200)): value = round(value + max(.25, math.sqrt(max(0, value)+16)/4)*rate, 2)
            value = max(old, value)
            memory["stats"][stat_key] = round(value, 2); gain = value-old
        elif discipline.casefold() == "combat" and isinstance(memory.get("power_score"), (int, float)):
            old = number(memory["power_score"]); value = old
            baseline = obj(obj(obj(before).get("npc_memories")).get(name)).get("power_score")
            if isinstance(baseline, (int, float)) and 0 <= baseline <= old: value = baseline
            for _ in range(min(months, 1200)): value = round(value + max(.25, math.sqrt(max(0, value)+16)/4)*rate, 2)
            value = max(old, value)
            memory["power_score"] = round(value, 2); gain = value-old
        expertise = life.setdefault("expertise", {})
        key = discipline or activity[:80]; expertise[key] = round(number(expertise.get(key)) + months*rate, 1)
        life.setdefault("history", []).append({"day": end, "activity": activity, "discipline": discipline, "months": months, "gain": round(gain, 2)})
        life["history"] = life["history"][-40:]
        for companion in seq(state.get("companions")):
            if isinstance(companion, dict) and text(companion.get("name")).casefold() == name.casefold():
                for key in ("stats", "power_score", "age"):
                    if key in memory: companion[key] = copy.deepcopy(memory[key])
        # No omniscient off-screen Chronicle notification. The next report or
        # conversation may reveal this ordinary development through real contact.
    for group in groups.values():
        if not isinstance(group, dict): continue
        leader = text(group.get("leader")); plan = obj(group.get("succession")); heir = text(plan.get("successor"))
        roster = obj(group.get("members")); previous = obj(roster.get(leader)); successor = obj(roster.get(heir))
        if not leader or not heir or not plan.get("accepted") or previous.get("status") not in {"retired", "dead", "deceased"}: continue
        if successor.get("status") not in {"active", "away"} or heir == leader: continue
        successor["position"] = previous.get("position", "Leader"); successor["reports_to"] = ""
        group["leader"] = heir
        for name, row in roster.items():
            if isinstance(row, dict) and name != heir and row.get("reports_to") == leader: row["reports_to"] = heir
        history(group, state, "succession", heir, f"Succeeded {leader} under the accepted succession plan.")
        group["succession"] = {}
        notices.append({"type": "organization", "title": f"{group['name']}: succession", "narrative": f"Under the agreed succession, {heir} takes over {leader}'s position in {group['name']}.", "importance": 65})
    sync_memberships(state, groups)
    return notices


def process_organizations(before, state, data, elapsed_minutes=0):
    # Preserve old memberships before a new nearby-companion list replaces them.
    if not state.get("organizations") and before.get("world") == state.get("world"):
        prior = membership_copy(before); ensure_organizations(prior)
        state["organizations"] = copy.deepcopy(prior.get("organizations", {}))
    apply_updates(state, data, campaign_day(before))
    return advance_lives(state, elapsed_minutes, before)


def roster_view(state):
    local = membership_copy(state); groups = ensure_organizations(local); output = []
    people = known_people(local)
    for group in groups.values():
        if not isinstance(group, dict): continue
        rows = []
        for name, raw in obj(group.get("members")).items():
            if not isinstance(raw, dict): continue
            life = obj(obj(local.get("organization_lives")).get(name)); memory = obj(people.get(name))
            rows.append({"name": name, "position": raw.get("position", "Member"), "status": raw.get("status", "active"),
                         "independent": raw.get("independent") is True,
                         "unit": raw.get("unit", ""), "reports_to": raw.get("reports_to", ""), "player": name == local.get("name"),
                         "power": power_for(local, name, raw, people), "age": memory.get("age", ""),
                         "notes": text(memory.get("notes")), "reason": raw.get("departure_reason") or (raw.get("membership_basis", "") if raw.get("membership_basis") != "Recorded campaign membership" else ""),
                         "terms": raw.get("terms", ""), "loyalty_basis": raw.get("loyalty_basis", ""),
                         "stage": life.get("stage", ""), "mentor": life.get("mentor", ""), "parents": life.get("parents", [])})
        rows.sort(key=lambda r: (r["status"] in FORMER, not r["player"], r["name"].casefold()))
        output.append({"id": group.get("id"), "name": group.get("name"), "type": label_for(local.get("world"), group.get("name", ""), group.get("kind", "")),
                       "leader": group.get("leader", ""), "members": rows, "history": seq(group.get("history"))[-12:],
                       "successor": obj(group.get("succession")).get("successor", "")})
    label = output[0]["type"] if len(output) == 1 else "Groups" if output else LABELS.get(state.get("world"), "Company")
    return {"label": label, "groups": output}


def organization_context(state, query=""):
    view = roster_view(state)
    selected = sorted(view["groups"], key=lambda g: (g["name"].casefold() not in query.casefold(),
                      not any(r["name"].casefold() in query.casefold() for r in g["members"])))[:6]
    return {"groups": [{"name": g["name"], "type": g["type"], "leader": g["leader"], "successor": g["successor"],
                        "member_count": len(g["members"]), "members": [
                            {k: (v[:300] if isinstance(v, str) else v) for k, v in r.items() if k not in {"notes", "reason"}}
                            for r in sorted(g["members"], key=lambda r: (r["name"].casefold() not in query.casefold(), not r["player"]))[:16]]} for g in selected],
            "life_development": {name: {k: copy.deepcopy(v[-4:] if k == "history" and isinstance(v, list) else v) for k, v in obj(row).items()}
                                 for name, row in list(obj(state.get("organization_lives")).items())[:100] if name.casefold() in query.casefold()}}


ORGANIZATION_RULE = """
ORGANIZATIONS AND LIVES: Membership is permanent until a real membership event, independent of proximity. Return organization_updates for established changes: group, event, name, reason and event-specific fields. Establish a named world-appropriate group with event=establish, kind and leader; do not create a crew/guild merely because someone met the player. Invite creates a candidate; join requires accepted=true and actual agreement. Positions, reports_to and unit express authority, never friendship or combat strength. Independent allies retain agency; subordinates preserve commands through their chain and actual communication.
Use event=position for rank/role changes; leave/retire/expel/death/away/return only when narratively established. Do not manufacture betrayal, departure, death, retirement or a crisis to fill a quota. Off-screen members train through development {activity, discipline, mentor, rate:routine|focused|exceptional, method, active}; discipline is an actual world stat or 'combat', and exceptional growth requires a real method. Noncombat expertise must not inflate combat power. No automatic matching to player stats, generic skill awards or fixed promotion trees.
Birth and life events preserve family, mentor, stage, aging_mode (mortal|ageless|immortal|spiritual|arrested) and maturity_age where known. Unknown ages stay unknown; no forced old-age death or compulsory retirement. Children and apprentices develop over actual elapsed time; no inherited mastery without learning. Succession_plan requires an established member and accepted=true; only a recorded death or voluntary retirement activates it. It changes the organization, never replaces the player's character. Public rosters show everyone associated, but hidden powers and distant secret activity are not revealed. Report developments through actual contact. NPC power_score/stats are same-world current estimates, never political rank alone.
"""
