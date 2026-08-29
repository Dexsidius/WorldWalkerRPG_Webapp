"""Local grounding, consequence reconciliation, and memory consolidation.

These helpers deliberately make no model calls.  They turn the durable save
into a small evidence packet for each AI job, verify narrated consequences
against mechanical state, and archive old campaign history without discarding
the facts later turns still need.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re

from util import ai_text


_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "did", "do", "does", "for", "from",
    "had", "has", "have", "how", "i", "in", "is", "it", "me", "my", "of", "on",
    "or", "that", "the", "this", "to", "was", "were", "what", "when", "where",
    "which", "who", "why", "with", "you", "your",
}


def _terms(value):
    return [word for word in re.findall(r"[a-z0-9'-]+", ai_text(value).lower())
            if len(word) > 1 and word not in _STOP]


def _score(query_terms, *values):
    blob = " ".join(ai_text(value).lower() for value in values)
    return sum(1 for term in query_terms if term in blob)


def _compact_memory(row):
    if not isinstance(row, dict):
        return {"text": ai_text(row)[:500]}
    return {key: copy.deepcopy(row.get(key)) for key in
            ("text", "source", "status", "turn", "first_turn", "last_turn", "canon_day")
            if row.get(key) not in (None, "", [], {})}


def build_grounding_packet(state, query="", purpose="moment", max_items=18):
    """Return a bounded, source-ranked set of facts every AI role must obey."""
    terms = _terms(query)
    special = state.get("special") if isinstance(state.get("special"), dict) else {}
    active_form = ((state.get("portrait_identity") or {}).get("active_form")
                   if isinstance(state.get("portrait_identity"), dict) else {}) or {}
    stats = state.get("stats") if isinstance(state.get("stats"), dict) else {}
    top_stats = sorted(((name, value) for name, value in stats.items()
                        if isinstance(value, (int, float)) and not isinstance(value, bool)),
                       key=lambda pair: (-pair[1], pair[0]))[:8]
    packet = {
        "source_priority": [
            "player corrections and current mechanical state",
            "confirmed campaign consequences and recent resolutions",
            "verified memory archive and chapter summaries",
            "opening-era canon only where the campaign has not diverged",
        ],
        "current_truth": {
            "name": state.get("name"), "world": state.get("world"),
            "turn": state.get("turn", 0), "time": state.get("world_time"),
            "canon_day": state.get("canon_day"), "location": state.get("location"),
            "position": state.get("position"), "alive": state.get("alive", True),
            "hp": [state.get("hp"), state.get("hp_max")],
            "resource": [state.get("resource_name"), state.get("resource"), state.get("resource_max")],
            "top_stats": top_stats, "affiliations": copy.deepcopy(state.get("affiliations", []))[:12],
            "active_form": copy.deepcopy(active_form),
            "combat": copy.deepcopy(state.get("combat", {})) if (state.get("combat") or {}).get("active") else {},
        },
        "locked_facts": copy.deepcopy((state.get("authoritative_corrections") or [])[-12:]),
        "relevant_people": [], "relevant_factions": [], "commitments": [],
        "verified_history": [], "consistency_rule": (
            "Answer and narrate from this packet first. Never replace a current campaign fact with stock canon. "
            "If two facts truly conflict, name the conflict instead of silently choosing one."
        ),
    }

    people = []
    companions = {ai_text(row.get("name") if isinstance(row, dict) else row).lower()
                  for row in state.get("companions", [])}
    for name, memory in (state.get("npc_memories") or {}).items():
        if not isinstance(memory, dict):
            continue
        priority = _score(terms, name, memory.get("goal"), memory.get("immediate_goal"), memory.get("last_known_location"))
        if ai_text(name).lower() in companions: priority += 8
        if memory.get("nemesis"): priority += 6
        if memory.get("last_known_location") == state.get("location"): priority += 5
        if not terms and (priority or memory.get("recurring")): priority += 1
        if priority:
            people.append((priority, {
                "name": name, "status": memory.get("status", "active"),
                "location": memory.get("last_known_location", "Unknown"),
                "attitude": memory.get("attitude", "Unknown"),
                "affiliation": memory.get("affiliation") or memory.get("faction"),
                "goal": memory.get("immediate_goal") or memory.get("goal") or memory.get("current_goal"),
                "power": memory.get("power_score", memory.get("power")),
                "nemesis": bool(memory.get("nemesis")), "companion": ai_text(name).lower() in companions,
                "recent_reasons": copy.deepcopy((memory.get("chain") or [])[-3:]),
            }))
    people.sort(key=lambda pair: (-pair[0], pair[1]["name"].lower()))
    packet["relevant_people"] = [row for _, row in people[:8]]

    affiliation_names = _affiliation_names(state)
    faction_names = set((state.get("factions") or {})) | set((state.get("faction_clocks") or {}))
    faction_names |= affiliation_names
    faction_rows = []
    for name in faction_names:
        clock = (state.get("faction_clocks") or {}).get(name, {})
        if not isinstance(clock, dict): clock = {}
        priority = _score(terms, name, clock.get("strategic_goal"), clock.get("immediate_goal"), clock.get("goal"))
        if name in affiliation_names: priority += 8
        if clock.get("opponent") or clock.get("status") == "turning_point": priority += 5
        if not terms and priority == 0: priority = 1
        if priority:
            faction_rows.append((priority, {
                "name": name, "standing": (state.get("reputation") or {}).get(name),
                "status": clock.get("status", "active"),
                "strategic_goal": clock.get("strategic_goal") or clock.get("core_ambition") or clock.get("goal"),
                "current_operation": copy.deepcopy(next((op for op in clock.get("operations", [])
                    if isinstance(op, dict) and op.get("status") == "active"), {})),
                "alliances": copy.deepcopy(clock.get("alliances", [])),
                "rivals": copy.deepcopy(clock.get("rivals", [])),
                "leader": copy.deepcopy(clock.get("leadership", {})),
            }))
    faction_rows.sort(key=lambda pair: (-pair[0], pair[1]["name"].lower()))
    packet["relevant_factions"] = [row for _, row in faction_rows[:6]]

    commitments = []
    for row in (state.get("standing_intents") or [])[-12:]:
        if isinstance(row, dict) and row.get("status", "active") == "active":
            commitments.append({"kind": "standing intent", "text": row.get("outcome") or row.get("directive") or row.get("text"), "owner": row.get("responsible")})
    for row in (state.get("narrative_memory") or {}).get("promises", [])[-8:]:
        if not isinstance(row, dict) or row.get("status", "active") == "active":
            commitments.append({"kind": "promise", **_compact_memory(row)})
    for quest in state.get("quests", []):
        if isinstance(quest, dict) and str(quest.get("status", "active")).lower() not in {"complete", "completed", "resolved", "failed", "archived"}:
            commitments.append({"kind": "quest", "name": quest.get("name"), "next": quest.get("next_hint") or quest.get("first_step")})
    packet["commitments"] = commitments[:12]

    history = []
    pools = [
        ("recent resolution", (state.get("resolution_ledger") or [])[-8:]),
        ("confirmed consequence", (state.get("consequence_ledger") or [])[-10:]),
        ("verified archive", (state.get("verified_memory_archive") or [])[-5:]),
        ("chapter", (state.get("chapter_summaries") or [])[-5:]),
        ("campaign", (state.get("campaign_canon") or [])[-16:]),
    ]
    for kind, rows in pools:
        for row in rows:
            if not isinstance(row, dict): continue
            title = row.get("title") or row.get("action") or row.get("kind") or kind
            body = row.get("summary") or row.get("outcome") or row.get("narrative") or row.get("evidence") or row.get("text")
            score = _score(terms, title, body)
            if not terms and kind in {"recent resolution", "confirmed consequence", "campaign"}: score = 1
            if score:
                history.append((score, int(row.get("turn") or (row.get("turns") or [0])[-1] or 0), {
                    "source": kind, "title": ai_text(title)[:180], "fact": ai_text(body)[:700],
                    "turn": row.get("turn") or (row.get("turns") or [None])[-1],
                }))
    history.sort(key=lambda item: (-item[0], -item[1]))
    packet["verified_history"] = [row for _, _, row in history[:max(4, min(24, int(max_items or 18)))]]
    return _prune(packet)


def _prune(value):
    if isinstance(value, dict):
        return {key: _prune(item) for key, item in value.items() if item not in (None, "", [], {})}
    if isinstance(value, list):
        return [_prune(item) for item in value if item not in (None, "", [], {})]
    return value


def _item_name(item):
    return ai_text(item.get("name") or item.get("title")) if isinstance(item, dict) else ai_text(item)


def _affiliation_names(state):
    names = set()
    for row in state.get("affiliations", []) or []:
        name = row.get("faction") if isinstance(row, dict) else row
        if ai_text(name):
            names.add(ai_text(name))
    return names


def _quest_by_name(state, name):
    wanted = ai_text(name).casefold()
    return next((quest for quest in state.get("quests", []) if isinstance(quest, dict)
                 and ai_text(quest.get("name") or quest.get("title")).casefold() == wanted), None)


def reconcile_narrated_consequences(before, state, data, actions=None, elapsed_minutes=5):
    """Apply safe omitted consequences and record every claim-to-state check.

    The narrator's consequence_manifest is preferred.  Structured event rows
    are also accepted as a backwards-compatible source.  Ambiguous mechanical
    claims are flagged rather than guessed.
    """
    data = data if isinstance(data, dict) else {}
    manifest = data.get("consequence_manifest") if isinstance(data.get("consequence_manifest"), list) else []
    for event in data.get("events", []) if isinstance(data.get("events"), list) else []:
        if not isinstance(event, dict): continue
        kind = ai_text(event.get("type")).lower()
        if kind not in {"skill", "title", "item", "loot", "quest", "location", "reputation", "companion", "injury", "death"}:
            continue
        target = event.get("target") or event.get("name")
        if target:
            manifest.append({"kind": kind, "target": target, "change": event.get("change") or event.get("status"), "evidence": event.get("message", "")})
    turn = int(state.get("turn", 0) or 0) + 1
    ledger = state.setdefault("consequence_ledger", [])
    rows, notes = [], []
    for raw in manifest[:40]:
        if not isinstance(raw, dict): continue
        kind = ai_text(raw.get("kind") or raw.get("type")).lower().replace(" ", "_")
        target = ai_text(raw.get("target") or raw.get("name") or raw.get("subject"))[:180]
        change = ai_text(raw.get("change") or raw.get("status") or raw.get("result"))[:120]
        evidence = ai_text(raw.get("evidence") or raw.get("reason") or data.get("narrative"))[:500]
        applied, status, reason = False, "verified", "Already reflected in state"
        if kind == "title" and target:
            names = {ai_text(item.get("name") or item.get("title") if isinstance(item, dict) else item).casefold() for item in state.get("titles", [])}
            if target.casefold() not in names:
                state.setdefault("titles", []).append(target); applied = True; reason = "Added omitted earned title"
        elif kind in {"item", "loot"} and target:
            names = {_item_name(item).casefold() for item in state.get("inventory", [])}
            removing = re.search(r"\b(?:lost|removed|spent|consumed|destroyed|gave away)\b", change + " " + evidence, re.I)
            if removing:
                old_len = len(state.get("inventory", [])); state["inventory"] = [item for item in state.get("inventory", []) if _item_name(item).casefold() != target.casefold()]
                applied = len(state["inventory"]) != old_len; reason = "Removed narrated item" if applied else "Item was not present"
            elif target.casefold() not in names:
                state.setdefault("inventory", []).append({"name": target, "description": ai_text(raw.get("description")) or "A notable item established by the Chronicle."})
                applied = True; reason = "Added omitted notable item"
        elif kind == "location" and target:
            if state.get("location") != target:
                state["location"] = target
                if target not in state.setdefault("discovered_locations", []): state["discovered_locations"].append(target)
                applied = True; reason = "Synchronized narrated travel"
        elif kind == "quest" and target:
            quest = _quest_by_name(state, target)
            completed = bool(re.search(r"\b(?:complete|completed|resolved|finished|cleared)\b", change + " " + evidence, re.I))
            if quest and completed and str(quest.get("status", "")).lower() not in {"complete", "completed", "resolved"}:
                quest["status"] = "Completed"; applied = True; reason = "Closed narrated quest"
            elif not quest and not completed:
                state.setdefault("quests", []).append({
                    "name": target, "status": "Active", "category": "personal",
                    "explanation": ai_text(raw.get("description")) or evidence or "A commitment established in the Chronicle.",
                    "current_knowledge": [], "clear_conditions": [], "first_step": ai_text(raw.get("next_step")),
                })
                applied = True; reason = "Added omitted narrative agenda"
        elif kind == "skill" and target:
            if target not in (state.get("skills") or {}):
                details = raw.get("details") if isinstance(raw.get("details"), dict) else {}
                if details.get("effect") or details.get("description"):
                    state.setdefault("skills", {})[target] = copy.deepcopy(details); applied = True; reason = "Added omitted fully described skill"
                else:
                    status = "needs_detail"; reason = "Narrative claims a skill but supplies no mechanics; retained as a validation warning"
        elif kind in {"injury", "condition"} and target:
            names = {ai_text(item.get("name") if isinstance(item, dict) else item).casefold() for item in state.get("conditions", [])}
            if target.casefold() not in names:
                state.setdefault("conditions", []).append({"name": target, "description": evidence or change, "source": "Chronicle"})
                applied = True; reason = "Applied omitted condition"
        elif kind == "death" and target and target.casefold() in {ai_text(state.get("name")).casefold(), "player", "the player"}:
            if state.get("alive", True): state["alive"], state["hp"], applied, reason = False, 0, True, "Synchronized narrated player death"
        else:
            status = "recorded"; reason = "Claim retained for grounding; no safe deterministic mutation"
        row = {"turn": turn, "kind": kind or "consequence", "target": target, "change": change,
               "evidence": evidence, "status": status, "applied_repair": applied, "reason": reason,
               "elapsed_minutes": int(elapsed_minutes or 0)}
        rows.append(row)
        if status == "needs_detail": notes.append(f"Consequence needs mechanics: {target}")

    # Always record exact mechanical deltas, even when the narrator supplied
    # no manifest.  This becomes the next turn's verified evidence.
    for key in ("location", "level", "xp", "hp", "resource"):
        if before.get(key) != state.get(key):
            rows.append({"turn": turn, "kind": key, "target": key, "change": f"{before.get(key)} → {state.get(key)}",
                         "evidence": "Authoritative state delta", "status": "verified", "applied_repair": False,
                         "reason": "Mechanical change confirmed", "elapsed_minutes": int(elapsed_minutes or 0)})
    for collection, kind in (("skills", "skill"), ("titles", "title")):
        old = before.get(collection, {})
        new = state.get(collection, {})
        old_names = set(old) if isinstance(old, dict) else {_item_name(item).casefold() for item in old or []}
        new_names = set(new) if isinstance(new, dict) else {_item_name(item).casefold() for item in new or []}
        for name in new_names - old_names:
            rows.append({"turn": turn, "kind": kind, "target": ai_text(name), "change": "gained",
                         "evidence": "Authoritative state delta", "status": "verified", "applied_repair": False,
                         "reason": "Mechanical change confirmed", "elapsed_minutes": int(elapsed_minutes or 0)})
    seen = set()
    for row in rows:
        key = (row["kind"], row["target"].casefold(), row["change"].casefold())
        if key in seen: continue
        seen.add(key); ledger.append(row)
    state["consequence_ledger"] = ledger[-240:]
    if notes:
        state.setdefault("simulation_validation", []).append({"turn": turn, "area": "consequence_reconciliation", "warnings": notes[:12]})
        state["simulation_validation"] = state["simulation_validation"][-100:]
    return {"checked": len(rows), "repairs": sum(bool(row.get("applied_repair")) for row in rows), "warnings": notes}


def _dedupe_memory_rows(rows):
    merged = {}
    for raw in rows if isinstance(rows, list) else []:
        row = copy.deepcopy(raw) if isinstance(raw, dict) else {"text": ai_text(raw)}
        text = re.sub(r"\s+", " ", ai_text(row.get("text") or row.get("summary") or row.get("fact"))).strip()[:700]
        if not text: continue
        key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        prior = merged.get(key)
        if prior:
            prior["first_turn"] = min(int(prior.get("first_turn", prior.get("turn", 0)) or 0), int(row.get("turn", 0) or 0))
            prior["last_turn"] = max(int(prior.get("last_turn", prior.get("turn", 0)) or 0), int(row.get("turn", 0) or 0))
            if row.get("status") not in (None, ""): prior["status"] = row["status"]
            continue
        row["text"], row["key"] = text, key
        row["first_turn"] = int(row.get("first_turn", row.get("turn", 0)) or 0)
        row["last_turn"] = int(row.get("last_turn", row.get("turn", 0)) or 0)
        merged[key] = row
    return sorted(merged.values(), key=lambda row: int(row.get("last_turn", 0) or 0))


def consolidate_long_campaign_memory(state, force=False):
    """Archive verified old turns and deduplicate durable memory locally."""
    turn = int(state.get("turn", 0) or 0)
    meta = state.setdefault("memory_consolidation", {"last_turn": 0, "archived_through_turn": 0, "runs": 0})
    canon = state.get("campaign_canon") if isinstance(state.get("campaign_canon"), list) else []
    memory = state.get("narrative_memory") if isinstance(state.get("narrative_memory"), dict) else {}
    oversized = len(canon) > 80 or any(len(rows) > 90 for rows in memory.values() if isinstance(rows, list))
    if not force and not oversized and turn - int(meta.get("last_turn", 0) or 0) < 12:
        return None
    for category, rows in list(memory.items()):
        if isinstance(rows, list): memory[category] = _dedupe_memory_rows(rows)[-100:]
    state["narrative_memory"] = memory

    archive = state.setdefault("verified_memory_archive", [])
    cutoff = max(0, turn - 50)
    already = int(meta.get("archived_through_turn", 0) or 0)
    candidates = [row for row in canon if isinstance(row, dict) and already < int(row.get("turn", 0) or 0) <= cutoff]
    new_archive = None
    if candidates:
        summary_parts = [ai_text(row.get("outcome") or row.get("text")) for row in candidates if ai_text(row.get("outcome") or row.get("text"))]
        actions = [ai_text(row.get("action")) for row in candidates if ai_text(row.get("action"))]
        payload = json.dumps(candidates, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
        new_archive = {
            "title": f"Verified turns {candidates[0].get('turn')}–{candidates[-1].get('turn')}",
            "turns": [candidates[0].get("turn"), candidates[-1].get("turn")],
            "canon_days": [candidates[0].get("canon_day"), candidates[-1].get("canon_day")],
            "summary": " ".join(summary_parts)[:5000], "key_actions": actions[-24:],
            "source_digest": hashlib.sha256(payload).hexdigest(), "verified": True,
        }
        archive.append(new_archive); state["verified_memory_archive"] = archive[-80:]
        meta["archived_through_turn"] = int(candidates[-1].get("turn", already) or already)
        # The archive is now the durable searchable copy. Keep a generous
        # recent tail in campaign_canon for the live Chronicle context.
        state["campaign_canon"] = [row for row in canon if not isinstance(row, dict) or int(row.get("turn", 0) or 0) > cutoff]
    meta["last_turn"], meta["runs"] = turn, int(meta.get("runs", 0) or 0) + 1
    meta["last_result"] = {"turn": turn, "archived": len(candidates), "memory_counts": {key: len(value) for key, value in memory.items() if isinstance(value, list)}}
    return copy.deepcopy(new_archive or meta["last_result"])
