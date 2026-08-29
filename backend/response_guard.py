"""Normalize untrusted model responses before gameplay code consumes them.

The state guard protects persisted state.  This module protects the *response
envelope* itself: inexpensive/local models often return useful shorthand such
as a string event, a single update object, or a string combatant.  Treat those
as recoverable input rather than allowing a later ``.get`` to end the turn.
"""
from __future__ import annotations

import copy

from state_guard import normalize_combat_payload
from util import ai_text


def _dict(value):
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _text_list(value, limit=40):
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        value = [value]
    return [ai_text(row).strip()[:700] for row in value[:limit] if ai_text(row).strip()]


def _event_list(value):
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        value = [value]
    rows = []
    for item in value[:80]:
        if isinstance(item, dict):
            row = copy.deepcopy(item)
            row["type"] = ai_text(row.get("type") or "world").strip() or "world"
            row["message"] = ai_text(row.get("message") or row.get("narrative") or row.get("text") or row.get("title")).strip()
        else:
            row = {"type": "world", "message": ai_text(item).strip()}
        if row.get("message"):
            rows.append(row)
    return rows


def _update_list(value):
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        value = [value]
    rows = []
    for index, item in enumerate(value[:120]):
        if isinstance(item, dict):
            row = copy.deepcopy(item)
            narrative = ai_text(row.get("narrative") or row.get("message") or row.get("text")).strip()
            title = ai_text(row.get("title") or row.get("type") or "Story Update").strip()
        else:
            narrative, title, row = ai_text(item).strip(), "Story Update", {}
        if not narrative:
            continue
        row.update({"narrative": narrative, "title": title or "Story Update"})
        row.setdefault("type", "story")
        row.setdefault("sequence", index)
        rows.append(row)
    return rows


def _chat_list(value):
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        value = [value]
    rows = []
    for item in value[:40]:
        if isinstance(item, dict):
            row = copy.deepcopy(item)
            row["sender"] = ai_text(row.get("sender") or row.get("thread") or "Unknown contact").strip()
            row["thread"] = ai_text(row.get("thread") or row.get("sender")).strip()
            row["message"] = ai_text(row.get("message") or row.get("text") or row.get("narrative")).strip()
        else:
            row = {"sender": "Unknown contact", "thread": "Unknown contact", "message": ai_text(item).strip()}
        if row.get("message"):
            rows.append(row)
    return rows


def normalize_assessment_response(value):
    data = _dict(value)
    checks = data.get("checks")
    if not isinstance(checks, list):
        checks = [checks] if isinstance(checks, dict) else []
    data["checks"] = [copy.deepcopy(row) for row in checks[:30] if isinstance(row, dict)]
    data["reachable_actions"] = _text_list(data.get("reachable_actions"))
    data["deferred_actions"] = _text_list(data.get("deferred_actions"))
    data["time_budget"] = _dict(data.get("time_budget"))
    return data


def normalize_turn_response(value, task="turn"):
    """Return a safe, meaning-preserving response envelope.

    A bare string is retained as narrative.  Nested structures are normalized
    only where the engine has a documented shape; unknown keys remain intact.
    """
    if isinstance(value, str):
        data = {"narrative": value}
    elif isinstance(value, dict):
        data = copy.deepcopy(value)
    else:
        data = {}
    data["narrative"] = ai_text(data.get("narrative") or data.get("story") or data.get("text")).strip()
    data["state_patch"] = _dict(data.get("state_patch"))
    if "combat" in data["state_patch"]:
        data["state_patch"]["combat"] = normalize_combat_payload(data["state_patch"].get("combat"))
    data["events"] = _event_list(data.get("events"))
    data["updates"] = _update_list(data.get("updates"))
    data["incoming_chats"] = _chat_list(data.get("incoming_chats"))
    data["suggested_actions"] = _text_list(data.get("suggested_actions"), 12)
    data["completed_actions"] = _text_list(data.get("completed_actions"))
    data["deferred_actions"] = _text_list(data.get("deferred_actions"))
    data["timeline_events"] = _text_list(data.get("timeline_events"))
    data["new_contacts"] = ([copy.deepcopy(row) for row in data.get("new_contacts", [])[:40]
                             if isinstance(row, dict)] if isinstance(data.get("new_contacts"), list) else [])
    for key in ("elapsed", "goal_status", "integrity_report"):
        if key in data:
            data[key] = _dict(data.get(key))
    for key in ("consequence_manifest", "commitment_updates", "delayed_consequences", "ability_developments"):
        value = data.get(key)
        data[key] = [copy.deepcopy(row) for row in value[:60] if isinstance(row, dict)] if isinstance(value, list) else []
    return data


def normalize_object_response(value, primary="reply"):
    """Make non-turn AI utilities safe without erasing their custom keys."""
    if isinstance(value, dict):
        data = copy.deepcopy(value)
    elif isinstance(value, str):
        data = {primary: value}
    else:
        data = {}
    if "state_patch" in data and not isinstance(data.get("state_patch"), dict):
        data["state_patch"] = {}
    if "events" in data:
        data["events"] = _event_list(data.get("events"))
    return data
