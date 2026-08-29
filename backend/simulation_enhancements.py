"""Local simulation depth added in v3.41.0.

The functions here never call an AI model.  They convert already-established
campaign state into bounded progression, dated Chronicle beats, communication
hooks, and prompt budgets.  Narration remains flexible while the underlying
facts stay persistent and inexpensive.
"""
from __future__ import annotations

import copy
import hashlib
import re

from util import ai_text


WORLD_DOWNTIME = {
    "Naruto": ("Shinobi Downtime", "Mission reports, intelligence, team practice, recovery, and village obligations continued around the active plan."),
    "Bleach": ("Division Routine", "Patrols, reports, Konso duties, training, and the Soul Society's chain of command continued between major incidents."),
    "One Piece": ("Voyage Between Headlines", "Navigation, shipboard routines, island rumors, newspapers, and crew responsibilities continued around the voyage."),
    "Hunter x Hunter": ("Hunter Work", "Research, contacts, travel, examinations, information trading, and Nen practice continued between major encounters."),
    "Jujutsu Kaisen": ("Jujutsu Duties", "Mission reports, residual analysis, barrier preparation, civilian protection, and headquarters pressure continued in the background."),
    "Overgeared": ("Satisfy Activity", "Quests, rankings, guild activity, NPC relationships, equipment upkeep, and class opportunities continued throughout Satisfy."),
    "Solo Max-Level Newbie": ("Tower Interval", "System notices, floor reconnaissance, hidden-condition research, rival movement, and build preparation continued between major clears."),
    "Reincarnated as a Slime": ("Nation and Household", "Subordinates, settlement work, trade, defense, naming obligations, and diplomacy continued without waiting for direct orders."),
    "Custom World": ("Life Between Turning Points", "Work, relationships, local obligations, recovery, and wider-world developments continued around the active plan."),
}

WORLD_MESSAGE_MEDIUM = {
    "Naruto": "mission report or messenger",
    "Bleach": "Hell Butterfly or division report",
    "One Piece": "Den Den Mushi, newspaper, or courier",
    "Hunter x Hunter": "call, message, or Hunter contact",
    "Jujutsu Kaisen": "phone message or headquarters report",
    "Overgeared": "Satisfy whisper or system mail",
    "Solo Max-Level Newbie": "system message or player contact",
    "Reincarnated as a Slime": "messenger, Thought Communication, or diplomatic report",
    "Custom World": "setting-appropriate message",
}


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _name(value):
    if isinstance(value, dict):
        return ai_text(value.get("name") or value.get("title") or value.get("label"))
    return ai_text(value)


def _fingerprint(*parts):
    return hashlib.sha256("|".join(ai_text(part).casefold() for part in parts).encode("utf-8")).hexdigest()[:16]


def normalize_dated_updates(updates, start_day, end_day, elapsed_minutes):
    """Give long-skip cards stable chronology without inventing story facts."""
    rows = [copy.deepcopy(row) for row in (updates or []) if isinstance(row, dict) and ai_text(row.get("narrative") or row.get("message"))]
    if not rows:
        return rows
    start_day, end_day = int(start_day or 0), int(end_day or start_day or 0)
    span = max(0, end_day - start_day)
    long_skip = int(elapsed_minutes or 0) >= 1440
    total = len(rows)
    for index, row in enumerate(rows):
        if long_skip and row.get("canon_day") in (None, ""):
            # Preserve authored ordering while spreading cards through the
            # interval. A one-card response remains anchored at the end.
            fraction = (index + 1) / max(1, total)
            row["canon_day"] = start_day + min(span, max(0, round(span * fraction)))
        row.setdefault("sequence", index + 1)
        row.setdefault("section", _update_section(row))
    return rows


def _update_section(row):
    blob = " ".join(ai_text(row.get(key)) for key in ("type", "title", "narrative", "related_action")).lower()
    if re.search(r"\b(train|practice|master|learn|level|xp|skill|class|evol)", blob): return "progression"
    if re.search(r"\b(message|letter|report|rumou?r|newspaper|broadcast)", blob): return "communication"
    if re.search(r"\b(companion|party|ally|relationship|bond)", blob): return "companions"
    if re.search(r"\b(canon|war|faction|village|kingdom|guild|world)", blob): return "world"
    return "story"


def advance_companion_autonomy(state, elapsed_minutes):
    """Advance delegated companion work and growth at milestone boundaries."""
    days = max(0.0, _number(elapsed_minutes) / 1440.0)
    if days <= 0:
        return []
    intents = [row for row in state.get("standing_intents", []) if isinstance(row, dict) and row.get("status", "active") == "active"]
    companions = state.get("companions") if isinstance(state.get("companions"), list) else []
    ledger = state.setdefault("companion_autonomy", {})
    events = []
    for companion in companions:
        if not isinstance(companion, dict) or not _name(companion):
            continue
        name = _name(companion)
        assigned = []
        for intent in intents:
            responsible = ai_text(intent.get("responsible") or intent.get("owner") or "").casefold()
            if responsible and (name.casefold() in responsible or responsible in {"party", "companions", "team", "crew"}):
                assigned.append(ai_text(intent.get("outcome") or intent.get("directive") or intent.get("text")))
        assigned.extend(ai_text(item) for item in companion.get("standing_orders", []) if ai_text(item))
        assigned = list(dict.fromkeys(item for item in assigned if item))
        if not assigned:
            continue
        if not isinstance(ledger.get(name), dict):
            ledger[name] = {"progress": 0.0, "milestone": 0, "history": []}
        row = ledger[name]
        previous = _number(row.get("progress"))
        loyalty = _number(companion.get("loyalty"), 50)
        health = ai_text(companion.get("condition") or "healthy").lower()
        condition_factor = .55 if any(word in health for word in ("injured", "wounded", "critical")) else 1.0
        gain = min(45.0, days * (1.1 + max(0.0, loyalty - 50.0) / 250.0) * condition_factor)
        current = min(100.0, previous + gain)
        row.update({"progress": round(current, 1), "directives": assigned[:4], "last_advanced_day": state.get("canon_day")})
        companion["autonomy_progress"] = round(current, 1)
        companion["active_directives"] = assigned[:4]
        milestone = int(current // 25)
        if milestone > int(row.get("milestone", 0) or 0):
            row["milestone"] = milestone
            development = f"{name} made meaningful independent progress on: {assigned[0]}"
            history = row.setdefault("history", [])
            history.append({"turn": state.get("turn", 0), "canon_day": state.get("canon_day"), "development": development})
            row["history"] = history[-20:]
            events.append({"type": "companion", "title": f"{name}'s Independent Progress", "narrative": development + ".", "importance": 58})
    state["companion_autonomy"] = ledger
    return events


def advance_npc_development(state, elapsed_minutes):
    """Let recurring NPCs develop from their own work, never from player scaling."""
    days = max(0.0, _number(elapsed_minutes) / 1440.0)
    if days < 1:
        return []
    registry = state.setdefault("npc_development", {})
    events = []
    companions = {_name(row).casefold() for row in state.get("companions", []) if _name(row)}
    for name, memory in (state.get("npc_memories") or {}).items():
        if not isinstance(memory, dict) or str(memory.get("status", "active")).lower() in {"dead", "deceased"}:
            continue
        goal = ai_text(memory.get("immediate_goal") or memory.get("goal") or memory.get("current_goal"))
        active = bool(memory.get("recurring") or memory.get("nemesis") or str(name).casefold() in companions)
        if not active:
            continue
        if not isinstance(registry.get(str(name)), dict):
            registry[str(name)] = {"progress": 0.0, "milestone": 0, "history": []}
        row = registry[str(name)]
        training = bool(re.search(r"\b(train|practice|study|learn|master|mission|fight|hunt|research|prepare)\w*\b", goal, re.I))
        rate = .9 if training else .35
        if memory.get("nemesis"): rate *= .65
        previous = _number(row.get("progress"))
        current = previous + min(30.0, days * rate)
        row.update({"progress": round(current, 1), "basis": goal or "Ongoing personal activity",
                    "last_advanced_day": state.get("canon_day"), "independent_of_player": True})
        memory["development_progress"] = round(current % 100, 1)
        milestone = int(current // 25)
        if milestone > int(row.get("milestone", 0) or 0):
            crossed = milestone - int(row.get("milestone", 0) or 0)
            row["milestone"] = milestone
            if training:
                old_bonus = _number(memory.get("development_bonus"), 0)
                power_gain = max(1.0, round((2.0 + min(8.0, _number(memory.get("power_score") or memory.get("power"), 20) * .025)) * crossed, 1))
                memory["development_bonus"] = round(old_bonus + power_gain, 1)
                row["power_growth"] = round(_number(row.get("power_growth"), 0) + power_gain, 1)
                if isinstance(memory.get("power_score"), (int, float)):
                    memory["power_score"] = round(_number(memory.get("power_score")) + power_gain, 1)
            detail = f"{name} has developed through {goal or 'their own continuing activity'}"
            row.setdefault("history", []).append({"turn": state.get("turn", 0), "canon_day": state.get("canon_day"), "detail": detail})
            row["history"] = row["history"][-20:]
            events.append({"type": "world", "title": f"{name} Develops", "narrative": detail + ".", "importance": 45})
    state["npc_development"] = registry
    return events


def record_ability_evolution(before, state, data, actions=None):
    """Persist an ability's applications and breakthroughs across the campaign."""
    ledger = state.setdefault("ability_evolution", {})
    authored = data.get("ability_developments") if isinstance(data, dict) and isinstance(data.get("ability_developments"), list) else []
    old_skills = before.get("skills") if isinstance(before.get("skills"), dict) else {}
    new_skills = state.get("skills") if isinstance(state.get("skills"), dict) else {}
    for name, detail in new_skills.items():
        if name not in old_skills:
            authored.append({"ability": name, "kind": "learned", "development": "Ability learned", "application": ""})
        elif isinstance(detail, dict) and isinstance(old_skills.get(name), dict):
            old_apps = {ai_text(item) for item in old_skills[name].get("applications", []) if ai_text(item)}
            for application in detail.get("applications", []) if isinstance(detail.get("applications"), list) else []:
                if ai_text(application) and ai_text(application) not in old_apps:
                    authored.append({"ability": name, "kind": "application", "development": "New application developed", "application": ai_text(application)})
    seen = set()
    for raw in authored[:30]:
        if not isinstance(raw, dict):
            continue
        ability = ai_text(raw.get("ability") or raw.get("name"))
        development = ai_text(raw.get("development") or raw.get("effect") or raw.get("kind"))
        if not ability or not development:
            continue
        key = _fingerprint(ability, development, raw.get("application"), state.get("turn"))
        if key in seen:
            continue
        seen.add(key)
        row = ledger.setdefault(ability, {"name": ability, "applications": [], "history": []})
        application = ai_text(raw.get("application"))
        if application and application.casefold() not in {ai_text(item).casefold() for item in row.get("applications", [])}:
            row.setdefault("applications", []).append(application)
        row.setdefault("history", []).append({
            "turn": int(state.get("turn", 0) or 0), "canon_day": state.get("canon_day"),
            "kind": ai_text(raw.get("kind") or "development"), "development": development[:500],
            "application": application[:300], "evidence": ai_text(raw.get("evidence") or "; ".join(actions or []))[:500],
        })
        row["applications"] = row.get("applications", [])[-30:]
        row["history"] = row.get("history", [])[-40:]
    state["ability_evolution"] = ledger
    return ledger


def world_downtime_events(state, elapsed_minutes, actions=None):
    days = max(0.0, _number(elapsed_minutes) / 1440.0)
    if days < 7:
        return []
    world = state.get("world", "Custom World")
    title, narrative = WORLD_DOWNTIME.get(world, WORLD_DOWNTIME["Custom World"])
    row = state.setdefault("world_downtime_cycles", {})
    if not isinstance(row, dict):
        row = state["world_downtime_cycles"] = {}
    prior_cycle = int(row.get("cycle", 0) or 0)
    cycle = prior_cycle + max(1, int(days // 7))
    row.update({"cycle": cycle, "last_canon_day": state.get("canon_day"), "world": world,
                "active_plan": [ai_text(item) for item in actions or [] if ai_text(item)][:4]})
    return [{"type": "downtime", "title": title, "narrative": narrative, "importance": 32}]


def reactive_communication(state, events, elapsed_minutes, existing=None):
    """Create at most one grounded incoming message from a real known contact."""
    if existing or int(elapsed_minutes or 0) < 1440:
        return []
    delivery = state.get("message_delivery_state") if isinstance(state.get("message_delivery_state"), dict) else {}
    turn = int(state.get("turn", 0) or 0)
    candidates = []
    companion_names = [_name(row) for row in state.get("companions", []) if _name(row)]
    for name in companion_names + list((state.get("contacts") or {}).keys()):
        if not name or name in candidates:
            continue
        contact = (state.get("contacts") or {}).get(name, {})
        if isinstance(contact, dict) and contact.get("can_contact", True) is False:
            continue
        delivery_row = delivery.get(name)
        if not isinstance(delivery_row, dict):
            delivery_row = {}
        if turn - int(delivery_row.get("last_incoming_turn", -99) or -99) >= 3:
            candidates.append(name)
    if not candidates:
        return []
    relevant_event = next((row for row in events if isinstance(row, dict) and _name(row.get("title")) and _number(row.get("importance"), 0) >= 40), None)
    if not relevant_event:
        return []
    sender = candidates[0]
    subject = ai_text(relevant_event.get("title") or "recent developments")
    medium = WORLD_MESSAGE_MEDIUM.get(state.get("world"), WORLD_MESSAGE_MEDIUM["Custom World"])
    return [{"thread": sender, "sender": sender,
             "message": f"A {medium} arrives from {sender}: they acknowledge {subject} and ask how you intend to respond.",
             "metadata": {"generated_locally": True, "source_event": subject, "medium": medium}}]


def apply_prompt_budget(snapshot, state, query="", purpose="moment", mode="balanced"):
    """Trim low-relevance payload tails and expose an auditable local budget."""
    out = copy.deepcopy(snapshot)
    limits = {
        "economy": {"chars": 32000, "skills": 18, "items": 20, "codex": 12, "threads": 5},
        "balanced": {"chars": 56000, "skills": 28, "items": 32, "codex": 20, "threads": 8},
        "deep": {"chars": 90000, "skills": 45, "items": 50, "codex": 35, "threads": 12},
    }.get(str(mode), {}) or {"chars": 56000, "skills": 28, "items": 32, "codex": 20, "threads": 8}
    terms = {word for word in re.findall(r"[a-z0-9'-]+", ai_text(query).lower()) if len(word) > 2}
    trimmed = {}

    def relevant_map(value, cap):
        if not isinstance(value, dict) or len(value) <= cap:
            return value
        ranked = []
        for index, (key, detail) in enumerate(value.items()):
            blob = f"{key} {detail}".lower()
            score = sum(term in blob for term in terms) * 100 - index / 1000
            ranked.append((score, index, key, detail))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        keep = sorted(ranked[:cap], key=lambda row: row[1])
        return {key: detail for _, _, key, detail in keep}

    if isinstance(out.get("skills"), dict):
        old = len(out["skills"]); out["skills"] = relevant_map(out["skills"], limits["skills"]); trimmed["skills"] = old - len(out["skills"])
    for key, cap in (("inventory", limits["items"]), ("codex", limits["codex"])):
        if isinstance(out.get(key), list) and len(out[key]) > cap:
            old = len(out[key]); out[key] = out[key][-cap:]; trimmed[key] = old - len(out[key])
    if isinstance(out.get("chat_threads"), dict) and len(out["chat_threads"]) > limits["threads"]:
        old = len(out["chat_threads"]); out["chat_threads"] = dict(list(out["chat_threads"].items())[-limits["threads"]:]); trimmed["chat_threads"] = old - len(out["chat_threads"])
    # The selected fields above dominate long-save growth. The remaining
    # estimate is recorded so later tuning can be evidence-based.
    estimated = len(repr(out))
    manifest = {"purpose": str(purpose), "mode": str(mode), "character_budget": limits["chars"],
                "estimated_characters": estimated, "trimmed": {k: v for k, v in trimmed.items() if v > 0},
                "rule": "Current mechanics, the live scene, named subjects, corrections, and recent consequences outrank old unrelated detail."}
    out["prompt_budget"] = manifest
    logs = state.setdefault("prompt_budget_log", [])
    logs.append({"turn": state.get("turn", 0), **copy.deepcopy(manifest)})
    state["prompt_budget_log"] = logs[-80:]
    return out
