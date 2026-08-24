"""Deterministic campaign-continuity ledger and contradiction warnings."""
import re
from datetime import datetime

from util import ai_text


def _quest_map(items):
    return {str(q.get("name", "")).lower(): q for q in items if isinstance(q, dict) and q.get("name")}


# A real player report: buying something in the narrative repeatedly left
# currency.amount untouched, and payment for work that should plausibly pay
# rarely showed up either. The GM prompt already says currency "must change
# with every transaction" (engine_core.py), but that's prose the model can
# just forget under schema pressure the same way it forgets other fields —
# this catches the mismatch after the fact so it can feed the same
# correction pass every other continuity warning already uses, rather than
# relying on the instruction alone.
_CURRENCY_SPEND_RE = re.compile(r"\b(buys?|bought|purchas\w*|pays? for|paid for|hands? over|handed over)\b", re.I)
_CURRENCY_EARN_RE = re.compile(
    r"\b(gets? paid|is paid|was paid|pays? (?:you|your|him|her|them|the)|receives? payment|"
    r"collects? (?:the|a|her|his|their) (?:reward|payment|fee|wages?)|"
    r"earns?|reward of|paid (?:him|her|them)|sells? it for|sold it for)\b", re.I,
)
_CURRENCY_NO_TRANSACTION_RE = re.compile(
    r"\b(declin\w*|refus\w*|can'?t afford|cannot afford|couldn'?t afford|too expensive|"
    r"decides? not to|chooses? not to|considers? buying|thinks? about buying)\b", re.I,
)
_CURRENCY_GENERIC_RE = re.compile(r"\b(coins?|gold|money|payment|reward|fee|wages?)\b", re.I)


def update_continuity(before, after, action="", narrative=""):
    ledger = after.setdefault("continuity_ledger", {"facts": [], "warnings": [], "last_checked_turn": 0})
    facts = ledger.setdefault("facts", [])
    warnings = []
    turn = after.get("turn", 0)
    stamp = {"turn": turn, "time": datetime.now().isoformat(timespec="seconds")}
    if before.get("location") != after.get("location"):
        facts.append({**stamp, "type": "location", "text": f"Player moved from {before.get('location')} to {after.get('location')}."})
    if before.get("appearance_desc") != after.get("appearance_desc"):
        facts.append({**stamp, "type": "appearance", "text": f"Current appearance: {after.get('appearance_desc')}."})
    new_titles = set(ai_text(t) for t in after.get("titles", []) if ai_text(t))
    old_titles = set(ai_text(t) for t in before.get("titles", []) if ai_text(t))
    for title in new_titles - old_titles:
        facts.append({**stamp, "type": "title", "text": f"Earned title: {title}."})
    old_quests, new_quests = _quest_map(before.get("quests", [])), _quest_map(after.get("quests", []))
    for key, quest in new_quests.items():
        old = old_quests.get(key)
        if not old:
            facts.append({**stamp, "type": "quest", "text": f"Quest accepted: {quest.get('name')}."})
        elif old.get("status") != quest.get("status"):
            facts.append({**stamp, "type": "quest", "text": f"{quest.get('name')} changed from {old.get('status')} to {quest.get('status')}."})
    names = [str(c.get("name", "")).lower() for c in after.get("codex", []) if isinstance(c, dict)]
    if len(names) != len(set(n for n in names if n)):
        warnings.append("The codex contains duplicate named entries.")
    for name, memory in after.get("npc_memories", {}).items():
        if isinstance(memory, dict) and memory.get("last_known_location") == "Unknown" and memory.get("can_contact"):
            warnings.append(f"{name} is contactable but has no known communication location/method.")
    # A quest silently un-completing (or un-failing) is almost always the AI
    # losing track of prior state rather than an intentional twist — a real
    # twist would say so in the narrative, which this can't see, so it only
    # flags the structural regression and lets the correction pass decide.
    for key, quest in new_quests.items():
        old = old_quests.get(key)
        if not old:
            continue
        old_status, new_status = str(old.get("status", "")).lower(), str(quest.get("status", "")).lower()
        if old_status in ("complete", "completed", "failed") and new_status not in (old_status, ""):
            warnings.append(f"Quest '{quest.get('name')}' regressed from {old_status} to {new_status} without explanation.")
    # A location that changed without the narrative ever naming the new place
    # is the clearest sign the AI moved the player mechanically (or forgot
    # where they were) rather than actually narrating travel.
    new_location = after.get("location")
    if before.get("location") != new_location and new_location and narrative:
        if str(new_location).lower() not in str(narrative).lower():
            warnings.append(f"Location changed to {new_location}, but the narrative never mentions arriving there.")
    # An NPC's last-known location updating in memory without ever being
    # named in this turn's narrative is the same class of silent drift.
    before_npc = before.get("npc_memories", {}) if isinstance(before.get("npc_memories"), dict) else {}
    after_npc = after.get("npc_memories", {}) if isinstance(after.get("npc_memories"), dict) else {}
    for name, memory in after_npc.items():
        if not isinstance(memory, dict):
            continue
        old_memory = before_npc.get(name) if isinstance(before_npc.get(name), dict) else {}
        new_loc = memory.get("last_known_location")
        if new_loc and new_loc != "Unknown" and new_loc != old_memory.get("last_known_location") and narrative:
            if str(name).lower() not in str(narrative).lower() and str(new_loc).lower() not in str(narrative).lower():
                warnings.append(f"{name}'s last-known location changed to {new_loc}, but neither is mentioned in the narrative.")
    currency_before = before.get("currency") if isinstance(before.get("currency"), dict) else {}
    currency_after = after.get("currency") if isinstance(after.get("currency"), dict) else {}
    if narrative and currency_before.get("amount") == currency_after.get("amount") and not _CURRENCY_NO_TRANSACTION_RE.search(narrative):
        currency_name = str(currency_after.get("name") or currency_before.get("name") or "").strip()
        currency_mentioned = (bool(currency_name) and currency_name.lower() in narrative.lower()) or bool(_CURRENCY_GENERIC_RE.search(narrative))
        if currency_mentioned and _CURRENCY_SPEND_RE.search(narrative):
            warnings.append(f"The narrative describes a purchase or payment being made, but currency.amount ({currency_after.get('amount')} {currency_name}) did not decrease.")
        elif currency_mentioned and _CURRENCY_EARN_RE.search(narrative):
            warnings.append(f"The narrative describes the player being paid, rewarded, or earning {currency_name or 'money'}, but currency.amount did not increase.")
    if action:
        after.setdefault("campaign_canon", []).append({**stamp, "action": str(action)[:500], "outcome": str(narrative)[:1200]})
        after["campaign_canon"] = after["campaign_canon"][-250:]
    ledger["facts"] = facts[-300:]
    ledger["warnings"] = warnings[-40:]
    ledger["last_checked_turn"] = turn
    return warnings
