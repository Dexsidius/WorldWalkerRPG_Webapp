"""Resolve offline state transitions in campaign-time order, not module order."""
from runtime_mode import offline_enabled
from offline_world import obj, definitions, tick as event_tick
from offline_politics import tick as petition_tick, tick_governments
from offline_governance import tick as budget_tick


def advance(s, before, after):
    if not offline_enabled() or after <= before:
        return set(), []
    moments = {after}
    def add(value):
        if isinstance(value, (int, float)) and before < value <= after:
            moments.add(int(value))
    from offline_canon_plans import definitions as plan_definitions
    for event in definitions(s) + plan_definitions(s):
        for key in ('depart', 'opens', 'due'):
            add(event[key])
    for row in obj(obj(s.get('offline_world')).get('appointments')).values():
        if not obj(row).get('aftermath_resolved'):
            add(obj(row).get('aftermath_due'))
    politics = obj(s.get('offline_politics'))
    for community in obj(politics.get('communities')).values():
        for petition in obj(community).get('petitions', []):
            if obj(petition).get('status') == 'pending':
                add(petition.get('due'))
    for holding in obj(politics.get('occupations')).values():
        if obj(holding).get('status') == 'charter_pending':
            add(holding.get('charter_due'))
    # These modules read the campaign clock for receipts and prerequisite checks.
    # Temporarily expose the boundary, then restore the caller's exact clock.
    saved = {key: s[key] for key in ('canon_time_minutes', 'canon_day') if key in s}
    owned, news, cursor = set(), [], before
    try:
        for minute in sorted(moments):
            s.update(canon_time_minutes=minute, canon_day=minute//1440)
            # Earn/spend budgets under the government that existed in the elapsed
            # interval, before ownership/charters change at its endpoint.
            news.extend(budget_tick(s, cursor, minute))
            ids, entries = event_tick(s, cursor, minute)
            owned.update(ids)
            news.extend(entries)
            # Same-time order is explicit: canon transition, petition, charter.
            news.extend(petition_tick(s, cursor, minute))
            news.extend(tick_governments(s, minute))
            cursor = minute
    finally:
        for key in ('canon_time_minutes', 'canon_day'):
            if key in saved:
                s[key] = saved[key]
            else:
                s.pop(key, None)
    return owned, sorted(news, key=lambda entry: entry.get('canon_day', 0))
