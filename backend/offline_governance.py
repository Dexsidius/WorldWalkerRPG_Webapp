"""Campaign-time government decisions and evidence-backed offline planning.

Civil budgets are abstract local simulation units, not invented military power.
Only established campaign forces and defenses can authorize an operation.
"""
import hashlib
from offline_world import obj, clock
from runtime_mode import offline_enabled

WEEK = 10080
WORLDS = {'Naruto', 'One Piece', 'Bleach'}


def enabled(s):
    return offline_enabled() and s.get('world') in WORLDS


def number(value, default=0):
    from military_resolution import numeric
    value = numeric(value)
    return default if value is None else value


def root(s):
    if not isinstance(s.get('offline_governance'), dict):
        s['offline_governance'] = {}
    r = s['offline_governance']
    for key in ('governments', 'plans'):
        if not isinstance(r.get(key), dict):
            r[key] = {}
    return r


def controlled(s):
    """Existing ownership only: never infer a whole country from village office."""
    places = {}
    for place, detail in obj(s.get('location_details')).items():
        owner = obj(detail).get('controlling_faction')
        if owner:
            places[place] = owner
    for place, occupation in obj(obj(s.get('offline_politics')).get('occupations')).items():
        if obj(occupation).get('status') == 'governed':
            places[place] = occupation['controller']
    return places


def tick(s, before, after):
    if not enabled(s) or after <= before:
        return []
    r = root(s)
    news = []
    for place, owner in sorted(controlled(s).items()):
        g = r['governments'].get(place)
        if not isinstance(g, dict) or g.get('owner') != owner:
            # Enroll from this campaign interval, not from the beginning of time.
            g = r['governments'][place] = dict(owner=owner, next_due=before+WEEK,
                treasury=20, services=50, order=50, policy='balanced', decisions=0)
        due = int(g['next_due'])
        if due > after:
            continue
        count = (after-due)//WEEK+1
        detail = obj(obj(s.get('location_details')).get(place))
        # Fixed weekly decisions; partitioning a time skip cannot change results.
        last = ''
        for _ in range(count):
            g['treasury'] = min(100, number(g['treasury'])+4)
            g['services'] = max(0, number(g['services'])-2)
            g['order'] = max(0, number(g['order'])-(4 if detail.get('contested_by') else 1))
            need = 'order' if g['policy'] == 'security' or g['order'] < 40 else 'services'
            if g[need] < 65 and g['treasury'] >= 6:
                g['treasury'] -= 6
                g[need] = min(100, g[need]+8)
                last = 'funded local patrol coordination' if need == 'order' else 'funded repairs and public services'
            else:
                last = 'retained reserves for future public needs'
            g['decisions'] += 1
        g['next_due'] = due+count*WEEK
        g['last_decision'] = last
        # No hidden polity reports. A local resident can observe local works.
        if place == s.get('location'):
            news.append({'text': f'[LOCAL GOVERNMENT]\n{owner} {last} at {place}.',
                'tag': 'system', 'canon_day': (g['next_due']-WEEK)//1440,
                'major': False, 'event_title': 'Local public works'})
    return news


def plans(s):
    return obj(obj(s.get('offline_governance')).get('plans'))


def actions(s, place):
    if not enabled(s):
        return []
    from politics import player_led_polities
    led = sorted(player_led_polities(s))
    result = []
    for faction in led:
        forces = obj(obj(s.get('faction_clocks')).get(faction))
        if number(forces.get('available_strength')) <= 0 and not forces.get('committed_forces'):
            strength = muster_strength(s, faction, place)
            if strength > 0:
                ident = hashlib.sha256(faction.encode()).hexdigest()[:16]
                result.append(dict(id='political:muster:'+ident, label='Muster '+faction+' members present here',
                    category='Politics', minutes=480, faction=faction, muster=True,
                    description=f'Organize {strength:g} explicitly recorded fighting strength from your local members. Unknown abilities and absent members are not counted.'))
    detail = obj(obj(s.get('location_details')).get(place))
    defender = detail.get('controlling_faction')
    if led and defender and defender not in led:
        # A survey can inspect an established garrison, not conjure numbers.
        strength = detail.get('defender_strength', detail.get('defender_power'))
        if number(strength, None) is not None:
            result.append(dict(id='political:survey', label='Survey the local garrison',
                category='Politics', minutes=480,
                description='Record established defenses and access at this location. Does not grant troops, supplies or a victory.'))
        plan = obj(plans(s).get(place))
        if plan.get('defender') == defender and plan.get('surveyed') is not None and clock(s)-plan['surveyed'] <= WEEK:
            for faction in led:
                force_record = obj(obj(s.get('faction_clocks')).get(faction))
                forces = force_record.get('available_strength')
                if number(forces) <= 0 or force_record.get('available_location') != place:
                    continue
                ident = hashlib.sha256(faction.encode()).hexdigest()[:16]
                cost = max(1, round(number(forces)*0.1, 2))
                result.append(dict(id='political:operation:'+ident,
                    label='Commit '+faction+' forces to the local holding', category='Politics',
                    minutes=480, cost=cost, currency=obj(s.get('currency')).get('name','currency'),
                    faction=faction, description=f'Commit {number(forces):g} recorded available strength; pay {cost:g} for supplies. Compare against surveyed defenses. Only one holding can be captured; defeat is possible.'))
    g = obj(obj(obj(s.get('offline_governance')).get('governments')).get(place))
    if g.get('owner') in led:
        for policy in ('balanced', 'security'):
            if policy != g.get('policy'):
                result.append(dict(id='political:policy:'+policy, label='Set local '+policy+' budget',
                    category='Politics', minutes=60, policy=policy,
                    description='Prioritize public services or local security in the next weekly budget. Does not create military units.'))
    return result


def resolve(s, spec):
    current = next((a for a in actions(s, spec['place']) if a['id'] == spec['id']), None)
    if not current:
        raise ValueError('The forces, defenses or authority changed. Refresh this activity.')
    place = spec['place']
    r = root(s)
    if current.get('muster'):
        faction = current['faction']
        clocks = s.setdefault('faction_clocks', {})
        forces = clocks.setdefault(faction, {})
        forces['available_strength'] = muster_strength(s, faction, place)
        forces['available_location'] = place
        s.setdefault('factions', {}).setdefault(faction, {})
        return f'{faction} musters {forces["available_strength"]:g} recorded fighting strength at {place}. No absent members or unrecorded powers were added.'
    if current.get('policy'):
        r['governments'][place]['policy'] = current['policy']
        return 'The next local budget at '+place+' will use the '+current['policy']+' policy.'
    detail = obj(obj(s.get('location_details')).get(place))
    if spec['id'] == 'political:survey':
        r['plans'][place] = dict(defender=detail['controlling_faction'], surveyed=clock(s),
            strength=number(detail.get('defender_strength', detail.get('defender_power'))),
            fortification=max(1, number(detail.get('fortification_multiplier'), 1)))
        return f'The survey at {place} records the existing garrison. The report is valid for seven days; changed defenses are rechecked before resolution.'
    from systems import record_currency_transaction
    from military_resolution import resolve_operation
    faction = current['faction']
    forces = s['faction_clocks'][faction]
    available = number(forces['available_strength'])
    plan = r['plans'][place]
    ident = hashlib.sha256(f'{faction}|{place}|{clock(s)}|{plan["surveyed"]}'.encode()).hexdigest()[:20]
    op = dict(id='offline-'+ident, type='military', opponent=plan['defender'], target_location=place,
        known_to_player=True, military_evidence=dict(basis='Local survey and recorded available forces; supplies purchased for this operation.',
            attacker_strength=available, defender_strength=plan['strength'],
            fortification_multiplier=plan['fortification'], access_confirmed=True, supplies_confirmed=True))
    result = resolve_operation(s, faction, forces, op)
    if op['status'] == 'awaiting_resolution':
        raise ValueError(op.get('blocked_reason', 'Further military evidence is required.'))
    record_currency_transaction(s, -current['cost'], 'Local operation supplies', 'military', source='offline_governance')
    # Forces are committed to the front, never reusable as an infinite army.
    forces['available_strength'] = 0
    forces.setdefault('committed_forces', {})[op['id']] = dict(strength=available, location=place,
        status='holding' if op['status']=='completed' else 'withdrawn', outcome=op['status'])
    r['plans'].pop(place, None)
    return op['recent_outcome']


def muster_strength(s, faction, place):
    roster = obj(s.get('faction_rosters')).get(faction, [])
    if not isinstance(roster, list):
        return 0
    names = {p if isinstance(p,str) else obj(p).get('name') for p in roster}
    total = 0
    for name in names:
        memory = obj(obj(s.get('npc_memories')).get(name))
        if (memory.get('alive') is False or memory.get('status') in {'dead','left','dismissed'}
                or memory.get('location') != place):
            continue
        total += number(memory.get('power_score'))
    return total
