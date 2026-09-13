"""Calendar-driven NPC appointments with authored choices and causal guards.

No model, wall-clock polling, random bad outcomes, or public schedule leakage.
All private state lives under offline_world, stripped by public_state().
"""
import hashlib
import re
import unicodedata
from functools import lru_cache

from runtime_mode import offline_enabled
from worlds import timeline_for
from canon_event_plans import catalog

TERMINAL = {'occurred', 'intervened', 'cancelled'}
LEGACY = {"Might Duy's sacrifice", 'Arlong Park revolt', "Aizen's betrayal at Sokyoku Hill"}


def obj(v):
    return v if isinstance(v, dict) else {}


def now(s):
    return int(s.get('canon_time_minutes', int(s.get('canon_day', 0))*1440+480))


def key_for(eid):
    return 'plan-'+hashlib.sha256(eid.encode()).hexdigest()[:16]


def rows(s):
    return obj(obj(s.get('offline_world')).get('plans'))


def writable(s):
    from offline_world import writable as root
    r = root(s)
    if not isinstance(r.get('plans'), dict):
        r['plans'] = {}
    return r['plans']


def writable_row(s, p):
    store = writable(s)
    if not isinstance(store.get(p['key']), dict):
        store[p['key']] = {'status': 'scheduled', 'title': p['title'], 'history': []}
    return store[p['key']]


def definitions(s):
    if not offline_enabled():
        return []
    authored = catalog(s.get('world'))
    out = []
    day_slots = {}
    for order, e in enumerate(timeline_for(s.get('world')).get('events', [])):
        slot = day_slots.get(e['day'], 0)
        day_slots[e['day']] = slot+1
        if e['title'] not in authored or e['title'] in LEGACY or e.get('historical_only'):
            continue
        eid = f"day:{e['day']}:{e['title']}"
        day = e['day']
        # Only exact event identity may move this appointment. Do not inherit
        # the old dependency graph's implicit previous-major-event chain.
        for d in s.get('canon_divergences', []):
            if isinstance(d, dict) and (d.get('event_id') == eid or d.get('title') == e['title']):
                if d.get('status') in {'delayed', 'delay'} and isinstance(d.get('new_day'), (int, float)):
                    day = int(d['new_day'])
        # Same-day beats are sequential, without changing any calendar day/ID.
        # Keep existing enrolled saves on their stored appointment time.
        due = day*1440+480+slot*180
        stored = obj(rows(s).get(key_for(eid)))
        if isinstance(stored.get('due'), (int, float)) and day == e['day']:
            due = int(stored['due'])
        out.append({**authored[e['title']], 'key': key_for(eid), 'event_id': eid,
                    'order': order, 'place': e['location'], 'due': due,
                    'opens': due-120, 'depart': due-1440,
                    'default': e.get('summary', ''), 'major': bool(e.get('major'))})
    return out


def available_record(s, p, before):
    anchor = s.get('calendar_anchor_day')
    return bool(obj(rows(s).get(p['key']))) or (
        p['due'] > before and p['event_id'] not in s.get('canon_events_fired', [])
        and (anchor is None or p['due'] >= int(anchor)*1440+480))


def normal(name):
    folded = unicodedata.normalize('NFKD', str(name)).encode('ascii', 'ignore').decode().casefold()
    return re.sub(r'[^a-z0-9]', '', folded)


def player_names(s):
    names = {identity_key(s, s.get('name'))}
    identity = obj(s.get('player_identity')).get('canon_character_id')
    if identity:
        name = start_names(s.get('world')).get(identity)
        if name:
            names.add(identity_key(s, name))
    return names


@lru_cache(maxsize=3)
def start_names(world):
    from worlds import playable_characters_for
    return {c['id']: c['name'] for c in playable_characters_for(world)}


@lru_cache(maxsize=3)
def identity_aliases(world):
    from canon_integrity import CANON_IDENTITIES
    aliases = {'ace':'portgasdace', 'akainu':'sakazuki', 'whitebeard':'edwardnewgate',
               'aizen':'sosukeaizen', 'ichigo':'ichigokurosaki', 'rukia':'rukiakuchiki',
               'orihime':'orihimeinoue', 'obito':'obitouchiha', 'asuma':'asumasarutobi'}
    for r in CANON_IDENTITIES.get(world, []):
        aliases.update({normal(n):normal(r['name']) for n in [r['name'], *r.get('aliases', [])]})
    return aliases


def identity_key(s, name):
    value = normal(name)
    return identity_aliases(s.get('world')).get(value, value)


def player_in_cast(s, p):
    # Matching a canon name is enough to avoid running a second copy of the
    # player, including older canon saves without the identity marker.
    return bool(player_names(s) & {identity_key(s, n) for n in p['actors']})


def positions(s):
    return obj(obj(s.get('offline_world')).get('actor_positions'))


def arrive(s, p):
    """Actual appointment positions are private, separate from last-known intel."""
    from offline_world import writable as root
    store = root(s)
    if not isinstance(store.get('actor_positions'), dict):
        store['actor_positions'] = {}
    for name in p['actors']:
        if identity_key(s, name) in player_names(s):
            continue
        store['actor_positions'][name] = {'location': p['place'], 'event_id': p['event_id'], 'minute': now(s)}
        if local(s, p, s.get('location')):
            for m in memories(s, name):
                m.update(last_known_location=p['place'])
                if 'location' in m:
                    m['location'] = p['place']


def memories(s, name):
    wanted = identity_key(s, name)
    for field in ('npc_memories', 'contacts'):
        for n, value in obj(s.get(field)).items():
            if identity_key(s, n) == wanted and isinstance(value, dict):
                yield value
    for value in s.get('companions', []):
        if isinstance(value, dict) and identity_key(s, value.get('name')) == wanted:
            yield value


def actor_unavailable(s, name, allow_captive=False):
    return obj(positions(s).get(name)).get('alive') is False or any(m.get('alive') is False or str(m.get('status', '')).casefold() in
               ({'dead', 'deceased', 'sealed'} if allow_captive else {'dead', 'deceased', 'captured', 'imprisoned', 'sealed'}) for m in memories(s, name))


def guard(s, p):
    recorded = obj(obj(s.get('canon_event_states')).get(p['event_id']))
    if recorded.get('status') in {'replaced', 'impossible', 'prevented', 'cancelled'}:
        return recorded.get('reason') or 'The campaign has already replaced this event.'
    for d in s.get('canon_divergences', []):
        if isinstance(d, dict) and (d.get('event_id') == p['event_id'] or d.get('title') == p['title']):
            if d.get('status') in {'prevented', 'cancelled', 'impossible', 'replaced', 'altered'}:
                return d.get('reason') or 'An earlier intervention changed this event.'
    for name in p['actors']:
        captive = name in p['captive_roles'] or p['rescue'] and name == p['rescue'][0]
        if actor_unavailable(s, name, allow_captive=captive):
            return name+' is unavailable; the original plan cannot proceed.'
    by_title = {r.get('title'): r for r in rows(s).values() if isinstance(r, dict)}
    for title in p['requires']:
        if obj(by_title.get(title)).get('status') in {'intervened', 'cancelled'}:
            return title+' changed. This dependent continuation needs a different plan.'
        # Also honor divergences in saves predating the appointment system.
        if any(isinstance(d, dict) and d.get('title') == title and d.get('status') in
               {'altered', 'prevented', 'replaced', 'cancelled', 'impossible'} for d in s.get('canon_divergences', [])):
            return title+' changed earlier in this campaign.'
        if any(str(eid).endswith(':'+title) and obj(value).get('status') in
               {'replaced', 'impossible', 'prevented', 'cancelled'}
               for eid, value in obj(s.get('canon_event_states')).items()):
            return title+' was replaced earlier in this campaign.'
    return ''


def local(s, p, place):
    if s.get('location') != place or p['place'] != place:
        return False
    if not p['private'] or player_in_cast(s, p):
        return True
    # Being in the same large city is not access to a secret meeting.
    return any(m.get('encounter_access') is True and
               (m.get('location') or m.get('last_known_location')) == place
               for n in p['actors'] for m in memories(s, n))


def finish(s, p, r, status, message):
    if r.get('status') in TERMINAL:
        return
    r.update(status=status, summary=message, resolved_minute=now(s))
    s.setdefault('canon_event_states', {})[p['event_id']] = {
        'status': 'occurred' if status == 'occurred' else 'replaced',
        'reason': message, 'resolved_day': now(s)//1440}
    fired = s.setdefault('canon_events_fired', [])
    if p['event_id'] not in fired:
        fired.append(p['event_id'])
    if status == 'intervened':
        s.setdefault('canon_divergences', []).append({
            'event_id': p['event_id'], 'title': p['title'], 'status': 'altered', 'reason': message})


def tick(s, before, after):
    owned, news = set(), []
    plans = sorted(definitions(s), key=lambda p: (p['due'], p['order']))
    for p in plans:
        # Own even old entries so the generic backstop cannot replay an expired
        # event on an old save. Do not rewrite that save's historical records.
        if p['due'] <= before and not rows(s).get(p['key']):
            continue
        if not available_record(s, p, before):
            continue
        # Do not enroll every future event at every turn. Start one day before.
        if after < p['depart'] and not rows(s).get(p['key']):
            continue
        owned.add(p['event_id'])
        r = writable_row(s, p)
        r['due'] = p['due']
        if r.get('status') in TERMINAL:
            continue
        reason = guard(s, p)
        if reason:
            finish(s, p, r, 'cancelled', reason)
            continue
        if r.get('status') == 'combat':
            continue
        if not isinstance(r.get('origins'), dict):
            r['origins'] = {name: obj(positions(s).get(name)).get('location') or
                            next((m.get('location') or m.get('last_known_location') for m in memories(s, name)
                                  if m.get('tracking_confirmed') is True), None) for name in p['actors']}
        if after >= p['opens']:
            # Reserve real actors for one active scene at a time. Adjacent beats
            # in the same place may coexist; different locations cannot.
            conflicting = next((q for q in plans if q['key'] != p['key'] and q['place'] != p['place']
                and obj(rows(s).get(q['key'])).get('status') == 'combat'
                and set(q['actors']) & set(p['actors'])), None)
            if conflicting:
                r.update(status='waiting', reason='A participant is still in an unresolved encounter elsewhere.')
                continue
            r['status'] = 'awaiting_player' if player_in_cast(s, p) else 'available'
            if not r.get('arrived'):
                arrive(s, p)
                r['arrived'] = True
        else:
            r['status'] = 'traveling'
        if after >= p['due'] and r['status'] != 'awaiting_player':
            message = p['default']
            finish(s, p, r, 'occurred', message)
            if p.get('rescue'):
                target = p['rescue'][0]
                # Rescue packs include detention as well as death. Only explicit
                # death titles produce a death, and never silently kill a player.
                if "death" in p['title'].casefold():
                    obj(positions(s).get(target)).update(alive=False)
                    for m in memories(s, target):
                        m.update(alive=False, status='dead')
            if not p['private'] or local(s, p, s.get('location')):
                news.append({'text': '[WORLD EVENT]\n'+message, 'tag': 'system',
                             'canon_day': p['due']//1440, 'major': False, 'event_title': p['title']})
    return owned, news


def live(s, p, place):
    r = obj(rows(s).get(p['key']))
    return (local(s, p, place) and not guard(s, p) and r.get('status') not in TERMINAL | {'combat', 'waiting'}
            and (p['opens'] <= now(s) < p['due'] and available_record(s, p, now(s))
                 or r.get('status') == 'awaiting_player'))


def boundary(s, start, end, place):
    stops = [(p['opens'], 'Local encounter — '+p['brief']) for p in definitions(s)
             if start < p['opens'] <= end and local(s, p, place) and not guard(s, p)
             and available_record(s, p, start) and obj(rows(s).get(p['key'])).get('status') not in TERMINAL]
    return min(stops) if stops else None


def actions(s, place):
    out = []
    for p in definitions(s):
        r = obj(rows(s).get(p['key']))
        prefix = 'worldevent:plan:'+p['key']+':'
        def add(verb, label, minutes, description):
            out.append({'id': prefix+verb, 'label': label, 'minutes': minutes,
                        'category': 'World', 'description': description})
        if local(s, p, place) and r.get('status') in TERMINAL and r.get('observed') and not r.get('reviewed'):
            add('review', 'Review this encounter', 0, r.get('summary', 'This encounter has ended.'))
        if not live(s, p, place) or r.get('declined'):
            continue
        flexible = r.get('status') == 'awaiting_player'
        if not r.get('observed') and (flexible or now(s)+10 < p['due']):
            add('observe', 'Assess the local situation', 10, p['brief']+' Records only what is observable here.')
        if not r.get('contributed') and (flexible or now(s)+30 < p['due']):
            add('contribute', p['offer'], 30, p['contribution']+' Takes thirty minutes; does not guarantee the canon outcome.')
        if p['rescue'] and not r.get('attempted'):
            target = p['rescue'][0]
            add('rescue', 'Protect '+target+' during a withdrawal', 0,
                f"Protect {target} for {3 if r.get('contributed') else 4} rounds. Starts tactical combat; success changes this event, not the entire conflict.")
        add('decline', 'Leave this encounter alone', 0,
            'No penalty for declining. Other people continue only if their original plan is still possible.'
            if not player_in_cast(s, p) else 'Do not follow the scheduled canon script. Your character is not moved or made to act.')
    return out


def view(s, place):
    out = []
    for p in definitions(s):
        r = obj(rows(s).get(p['key']))
        if not local(s, p, place) or r.get('reviewed') or r.get('declined'):
            continue
        if not live(s, p, place) and not (r.get('observed') and r.get('status') in TERMINAL | {'combat'}):
            continue
        # Never put secret revelations (or the timeline's spoiler title) in a
        # scene header before they occur.
        title = 'Local canon encounter' if p['private'] else p['title']
        known = [n for n in p['actors'] if not p['private'] or list(memories(s, n)) or normal(n) == normal(s.get('name'))]
        out.append({'title': title, 'kind': 'Canon encounter', 'authorship': 'Authored local branch; calendar timing is a game convention',
                    'stage': 'aftermath' if r.get('status') in TERMINAL else 'combat' if r.get('status') == 'combat' else 'decision',
                    'narrative': r.get('summary') if r.get('status') in TERMINAL else p['brief'],
                    'place': place, 'person': ', '.join(known), 'basis': 'Present at the encounter',
                    'prepared': bool(r.get('contributed')), 'prefix': 'worldevent:plan:'+p['key']+':',
                    'key': p['key'], 'changes': [p['contribution']] if r.get('contributed') else [],
                    'history': r.get('history', [])})
    return out


def resolve(game, spec):
    s = game.state
    parts = spec['id'].split(':')
    p = next((p for p in definitions(s) if len(parts) == 4 and p['key'] == parts[2]), None)
    if not p or not local(s, p, spec['place']):
        raise ValueError('This encounter is not accessible here.')
    verb = parts[-1]
    # Timed actions have already consumed their quoted duration. Revalidate the
    # remaining scene, not a second copy of that duration.
    r = obj(rows(s).get(p['key']))
    if verb in {'observe', 'contribute'}:
        if not live(s, p, spec['place']) or r.get('declined') or r.get('observed' if verb == 'observe' else 'contributed'):
            raise ValueError('This encounter changed before that task could be completed.')
    elif not any(a['id'] == spec['id'] for a in actions(s, spec['place'])):
        raise ValueError('This encounter choice is no longer available.')
    r = writable_row(s, p)
    if verb == 'review':
        r['reviewed'] = True
        return r['summary']
    if verb == 'decline':
        r['declined'] = True
        if player_in_cast(s, p):
            finish(s, p, r, 'intervened', 'You chose not to follow this scheduled canon plan. Your next action remains yours to choose.')
        return 'You leave the encounter alone. No relationship penalty is applied.'
    r['observed'] = True
    if verb == 'observe':
        message = p['brief']
    elif verb == 'contribute':
        r['contributed'] = True
        message = p['contribution']
        # A real, bounded contribution is available to later offline branches;
        # no currency, authority, technique, or relationship is invented.
    else:
        target, enemy, power, count = p['rescue']
        r.update(status='combat', attempted=True)
        s['combat'] = {'active': True, 'tactical_enabled': True, 'cause': p['brief'],
                       'enemy': {'name': enemy, 'power': power, 'hp': power*2*count, 'hp_max': power*2*count,
                                 'is_group': count > 1, 'group_size': count},
                       'adventure_objective': {'kind': 'protection', 'world_event': p['key'], 'target_label': target,
                          'rounds_required': 3 if r.get('contributed') else 4, 'rounds_survived': 0,
                          'target_hp': 60, 'target_hp_max': 60, 'settled': False}, 'log': []}
        game.ensure_combat_numbers()
        from tactical_combat import ensure_board
        ensure_board(s)
        game.acknowledge_danger_scenario(p['brief'])
        message = 'Protect '+target+' until the withdrawal is complete. Defeating a whole faction is not required or awarded.'
    r.setdefault('history', []).append({'title': spec['label'], 'text': message, 'minute': now(s)})
    return message


def combat_finished(game, outcome):
    s = game.state
    goal = obj(obj(s.get('combat')).get('adventure_objective'))
    if goal.get('settled'):
        return
    p = next((p for p in definitions(s) if p['key'] == goal.get('world_event')), None)
    if not p:
        raise ValueError('Missing canon rescue definition.')
    goal['settled'] = True
    r = writable(s)[p['key']]
    if outcome == 'objective_complete' and not actor_unavailable(s, p['rescue'][0], allow_captive=True):
        message = p['rescue'][0]+' reaches safety under your protection. The original outcome of this encounter has changed; the wider conflict is not automatically won.'
        finish(s, p, r, 'intervened', message)
        for m in memories(s, p['rescue'][0]):
            if str(m.get('status', '')).casefold() in {'captured', 'imprisoned'}:
                m['status'] = 'recovering'
    else:
        r['status'] = 'available'
        message = 'The withdrawal was not secured. The scheduled outcome has not been prevented, and no death is applied before its deadline.'
    game.append(message, 'narrative', canon_day=s.get('canon_day'))


def visible_parties(s):
    """At most one marker per actor, with no private or unconfirmed live tracking."""
    from offline_world import route_position
    allies = {normal(c.get('name')) for c in s.get('companions', []) if isinstance(c, dict)
              and c.get('alive') is not False and c.get('status') not in {'dead', 'left', 'dismissed'}}
    for affiliation in s.get('affiliations', []):
        a = obj(affiliation)
        if a.get('status') in {'left', 'dismissed', 'inactive'}:
            continue
        roster = obj(s.get('faction_rosters')).get(a.get('faction') or a.get('name'), [])
        if isinstance(roster, list):
            allies.update(normal(n if isinstance(n, str) else obj(n).get('name')) for n in roster
                          if isinstance(n, str) or obj(n).get('alive') is not False and obj(n).get('status') not in {'dead', 'left', 'dismissed'})
    out, seen = [], set()
    for p in sorted(definitions(s), key=lambda p: (p['due'], p['order'])):
        r = obj(rows(s).get(p['key']))
        if r.get('status') not in {'traveling', 'available', 'combat', 'awaiting_player'} or guard(s, p):
            continue
        here = r['status'] != 'traveling' and local(s, p, s.get('location'))
        for name in p['actors']:
            if identity_key(s, name) in seen or identity_key(s, name) in player_names(s) or actor_unavailable(s, name, allow_captive=name in p['captive_roles'] or p['rescue'] and name == p['rescue'][0]):
                continue
            if p['private'] and not list(memories(s, name)):
                continue
            route = None
            if not here:
                m = next((m for m in memories(s, name) if m.get('tracking_confirmed') is True), {})
                if normal(name) not in allies or not m:
                    continue
                origin = obj(r.get('origins')).get(name) or m.get('location') or m.get('last_known_location')
                route = route_position(s, {**p, 'origin': origin}) if origin else None
                if not route:
                    continue
            item = {'name': name, 'last_known_location': p['place'] if here else origin,
                    'label': 'Witnessed participant' if here else 'Confirmed party movement',
                    'goal': p['brief'] if here else 'Following the confirmed route.',
                    'event_id': p['key'], 'score': 0,
                    'knowledge': ['Present at this encounter'] if here else ['Confirmed travel report']}
            if route:
                item.update(route)
            out.append(item)
            seen.add(identity_key(s, name))
    return out
