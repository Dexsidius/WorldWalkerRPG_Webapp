"""Authoritative validation for AI-authored campaign state patches.

The GM may propose any world-consistent outcome, but it cannot directly write
application-owned fields, change the clock outside Advance, or corrupt the save
shape. Every accepted/rejected field is recorded for Diagnostics.
"""
import copy
from datetime import datetime

from util import merge, ai_text
from worlds import BASE_STATE, DIFFICULTIES, WORLD_DATA, abilities_for


APP_OWNED = {
    "turn", "campaign_id", "campaign_created_version", "campaign_last_saved_version",
    "schema_version", "validation_log", "diagnostics", "last_autosave",
    # Mechanically maintained bookkeeping (continuity.py, systems.py, the
    # canon-timeline firing logic) — the GM sees these in "state" for context
    # but must never author them itself. Without this guard a model that
    # mimics the shape of its own context can duplicate a campaign_canon
    # entry the mechanical system is about to append anyway, and a weaker
    # local model burning its limited output budget re-typing these back
    # verbatim is a real contributor to truncated, invalid JSON.
    "campaign_canon", "continuity_ledger", "chapter_summaries", "chapter_buffer",
    "canon_events_fired", "pending_minor_events",
    # Fixed once at campaign creation to whatever start_day this campaign
    # actually began on (a canon character's birth, a chosen starting era,
    # or the world default) — every calendar date shown for the rest of the
    # campaign is computed relative to it. It has no type validation of its
    # own (BASE_STATE's default is None), so a model that echoes it back
    # from context could silently corrupt every date in the campaign.
    "calendar_anchor_day", "last_protagonist_tick_day", "active_canon_event",
    # Deterministic pacing bookkeeping (systems.tick_world_clocks/pacing_guidance)
    # and the player's own standing preference field — both set only through
    # their own dedicated mechanism/endpoint, never through the GM's own
    # narrated state_patch.
    "last_major_beat_day", "director_notes",
    # The permanent "why reputation moved" trail (continuity.py) — the GM
    # supplies a one-line reason via reputation_chain_events each turn, but
    # never authors the accumulated faction_chain history directly.
    "faction_chain",
    # The permanent, app-owned purchase-offer ledger (systems.py) — the GM
    # supplies a one-turn purchase_offer, but never authors the resolved
    # flag or ids in purchase_offers directly.
    "purchase_offers",
    # Only the player's own rating action (engine_journal.rate_last_turn_good)
    # writes this — never the GM.
    "rated_good_turns",
}
TIME_OWNED = {"world_time", "world_clock_minutes", "calendar", "canon_time_minutes", "canon_day"}
FLEXIBLE_TYPES = {"age", "current_activity", "position"}


def _type_ok(key, value):
    if key in FLEXIBLE_TYPES:
        return value is None or isinstance(value, (str, int, float, dict))
    expected = BASE_STATE.get(key)
    if isinstance(expected, bool):
        return isinstance(value, bool)
    if isinstance(expected, int):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(expected, str):
        return isinstance(value, str)
    if isinstance(expected, list):
        return isinstance(value, list)
    if isinstance(expected, dict):
        return isinstance(value, dict)
    return True


def _clean_quest(raw, hidden=False):
    if isinstance(raw, str):
        raw = {"name": raw, "explanation": "No briefing recorded yet."}
    if not isinstance(raw, dict) or not str(raw.get("name") or raw.get("title") or "").strip():
        return None
    q = copy.deepcopy(raw)
    q["name"] = str(q.get("name") or q.get("title")).strip()[:160]
    q["status"] = str(q.get("status") or ("Hidden" if hidden else "Active"))[:40]
    q["category"] = str(q.get("category") or ("hidden" if hidden else "side")).lower()
    if q["category"] not in {"main", "side", "personal", "hidden"}:
        q["category"] = "side"
    q["explanation"] = str(q.get("explanation") or q.get("description") or "No additional explanation is known yet.")[:2000]
    aliases = {
        "current_knowledge": ("current_knowledge", "knowledge", "clues", "known_facts"),
        "clear_conditions": ("clear_conditions", "completion_conditions", "conditions", "objectives"),
        "evidence": ("evidence", "clues"), "involved_npcs": ("involved_npcs", "npcs"),
        "locations": ("locations",), "consequences": ("consequences",),
    }
    for target, keys in aliases.items():
        value = next((q.get(k) for k in keys if q.get(k) is not None), [])
        if isinstance(value, str):
            value = [value]
        q[target] = [ai_text(x)[:500] for x in value[:40] if ai_text(x)] if isinstance(value, list) else []
    q["deadline"] = q.get("deadline") or None
    raw_objectives = q.get("objectives", q.get("clear_conditions", []))
    if isinstance(raw_objectives, str):
        raw_objectives = [raw_objectives]
    q["objectives"] = copy.deepcopy(raw_objectives[:40]) if isinstance(raw_objectives, list) else []
    branch = q.get("branch_state")
    q["branch_state"] = copy.deepcopy(branch) if isinstance(branch, dict) else {"current": "main", "available": [], "locked": []}
    q["first_step"] = str(q.get("first_step") or q.get("next_step") or "")[:500]
    q["player_notes"] = str(q.get("player_notes") or "")[:4000]
    return q


def _normalize_patch(patch, before, allow_time=False, source="gm"):
    safe, accepted, rejected = {}, [], []
    if not isinstance(patch, dict):
        return {}, accepted, [{"field": "<root>", "reason": "state_patch was not an object"}]
    for key, value in patch.items():
        if key not in BASE_STATE:
            rejected.append({"field": key, "reason": "unknown state field"})
            continue
        if key in APP_OWNED or (key in TIME_OWNED and not allow_time):
            rejected.append({"field": key, "reason": "application-owned field"})
            continue
        if key in {"world", "difficulty"} and value != before.get(key):
            rejected.append({"field": key, "reason": "campaign identity cannot be rewritten by the GM"})
            continue
        if not _type_ok(key, value):
            rejected.append({"field": key, "reason": f"invalid type {type(value).__name__}"})
            continue
        if key == "stats":
            allowed = set(abilities_for(before.get("world", "Custom World")))
            value = {str(k): max(1, int(v)) for k, v in value.items() if k in allowed and isinstance(v, (int, float))}
        elif key in {"quests", "hidden_quests", "quest_archive"}:
            cleaned = [_clean_quest(q, key == "hidden_quests") for q in value[:200]]
            value = [q for q in cleaned if q]
        elif isinstance(value, list):
            value = value[:500]
        safe[key] = copy.deepcopy(value)
        accepted.append(key)
    return safe, accepted, rejected


def _repair(state):
    repairs = []
    if state.get("world") not in WORLD_DATA:
        state["world"] = "Custom World"; repairs.append("Unknown world changed to Custom World")
    if state.get("difficulty") not in DIFFICULTIES:
        state["difficulty"] = "Adventurer"; repairs.append("Unknown difficulty changed to Adventurer")
    for current, maximum in (("hp", "hp_max"), ("resource", "resource_max")):
        try:
            state[maximum] = max(1, int(state.get(maximum, 100)))
            state[current] = max(0, min(state[maximum], int(state.get(current, state[maximum]))))
        except (TypeError, ValueError):
            state[maximum], state[current] = 100, 100
            repairs.append(f"Repaired invalid {current}/{maximum}")
    state["alive"] = bool(state.get("alive", True) and state.get("hp", 0) > 0)
    for key, default in BASE_STATE.items():
        if key not in state:
            state[key] = copy.deepcopy(default); repairs.append(f"Restored missing {key}")
    if state.get("location") and state["location"] not in state.setdefault("discovered_locations", []):
        state["discovered_locations"].append(state["location"])
        repairs.append("Added current location to discovered locations")
    return repairs


def apply_guarded_patch(state, patch, allow_time=False, source="gm"):
    safe, accepted, rejected = _normalize_patch(patch, state, allow_time, source)
    merge(state, safe)
    repairs = _repair(state)
    report = {
        "time": datetime.now().isoformat(timespec="seconds"), "turn": state.get("turn", 0),
        "source": source, "accepted": accepted, "rejected": rejected, "repairs": repairs,
    }
    state.setdefault("validation_log", []).append(report)
    state["validation_log"] = state["validation_log"][-100:]
    return report


def migrate_state(state, from_version="unknown"):
    migrated = copy.deepcopy(state) if isinstance(state, dict) else {}
    old_schema = int(migrated.get("schema_version", 0) or 0)
    if old_schema < 5 and isinstance(migrated.get("stats"), dict):
        # Convert the former 3-20 D&D-like scale to the open-ended local scale
        # while preserving relative strengths. Pool damage/resource ratios are
        # retained below instead of healing old saves for free.
        migrated["stats"] = {k: max(1, int(v) * 3) for k, v in migrated["stats"].items() if isinstance(v, (int, float))}
        world = migrated.get("world", "Custom World")
        pool_map = {
            "One Piece": (("Endurance", "Willpower"), ("Willpower", "Instinct")),
            "Hunter x Hunter": (("Strength", "Willpower"), ("Aura Control", "Willpower")),
            "Naruto": (("Taijutsu", "Willpower"), ("Chakra Control", "Ninjutsu")),
            "Reincarnated as a Slime": (("Instinct", "Willpower"), ("Magicule Control", "Skill Mastery")),
        }
        hp_keys, resource_keys = pool_map.get(world, (("Constitution", "Strength"), ("Wisdom", "Intelligence")))
        stats = migrated["stats"]
        hp_new = max(20, 25 + int(stats.get(hp_keys[0], 30)) * 2 + int(stats.get(hp_keys[1], 30)))
        resource_new = max(10, 15 + int(stats.get(resource_keys[0], 30)) * 2 + int(stats.get(resource_keys[1], 30)))
        hp_ratio = float(migrated.get("hp", 100) or 0) / max(1, float(migrated.get("hp_max", 100) or 100))
        resource_ratio = float(migrated.get("resource", 100) or 0) / max(1, float(migrated.get("resource_max", 100) or 100))
        migrated.update(hp_max=hp_new, hp=max(0, round(hp_new * hp_ratio)),
                        resource_max=resource_new, resource=max(0, round(resource_new * resource_ratio)))
    for key, default in BASE_STATE.items():
        migrated.setdefault(key, copy.deepcopy(default))
    migrated["schema_version"] = BASE_STATE.get("schema_version", 6)
    repairs = _repair(migrated)
    migrated.setdefault("diagnostics", {})["migration"] = {
        "from_version": from_version, "repairs": repairs,
        "time": datetime.now().isoformat(timespec="seconds"),
    }
    return migrated
