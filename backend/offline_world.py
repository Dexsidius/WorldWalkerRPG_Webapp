"""Authored offline canon appointments. No wall-clock simulation or AI calls.

The campaign calendar remains authoritative. Reads never initialize a save;
old saves enroll only future appointments, never replay already completed history.
Travel/intervention windows are game conventions, not claimed canonical dates.
"""
import heapq

from runtime_mode import offline_enabled
from worlds import timeline_for

PACKS = {
    'Naruto': [{
        'key': 'duy', 'title': "Might Duy's sacrifice", 'origin': 'Konohagakure',
        'actors': ['Might Duy', 'Might Guy', 'Ebisu', 'Genma Shiranui'],
        'enemy': 'Seven Ninja Swordsmen of the Mist', 'power': 350, 'count': 7,
        'offer': 'Protect the retreat before Duy opens the Eighth Gate',
        'brief': 'Guy, Ebisu and Genma need a way out. Hold the pursuit for four rounds so Duy can withdraw without opening the Gate of Death.',
        'saved': 'The team escapes under your protection. Duy withdraws without opening the Eighth Gate and survives.',
        'default': 'Duy opens the Eighth Gate to protect Guy, Ebisu and Genma. The team escapes, but Duy dies from the Gate of Death.',
        'death': 'Might Duy',
    }],
    'One Piece': [{
        'key': 'arlong', 'title': 'Arlong Park revolt', 'origin': 'Cocoyasi Village',
        'actors': ['Nami', 'Genzo', 'Nojiko'], 'enemy': 'Arlong Pirates', 'power': 110, 'count': 4,
        'offer': 'Protect the villagers during the revolt',
        'brief': 'Hold off the raiders for four rounds while the villagers escape the fighting. This does not make you ruler of their island.',
        'saved': 'The villagers reach safety under your protection. Arlong’s occupation is not ended by this rescue alone; his defeat remains a separate event.',
        'default': 'The Straw Hats defeat Arlong and end his occupation. Nami joins their crew.',
    }],
    'Bleach': [{
        'key': 'sokyoku', 'title': "Aizen's betrayal at Sokyoku Hill", 'origin': 'Seireitei',
        'actors': ['Rukia Kuchiki', 'Renji Abarai'], 'enemy': 'Execution detail', 'power': 180, 'count': 4,
        'offer': 'Cover Rukia and Renji’s escape from the execution ground',
        'brief': 'Protect the escape route for four rounds. This changes your part in the rescue; it does not automatically defeat Aizen or cancel his plans.',
        'saved': 'You cover Rukia and Renji’s escape from the execution ground. This has not defeated Aizen or exposed his conspiracy to anyone who did not witness it.',
        'default': 'Ichigo interrupts the execution. Aizen exposes his conspiracy at Sokyoku Hill and defects with Gin and Tosen.',
    }],
}


def obj(value):
    return value if isinstance(value, dict) else {}


def clock(s):
    return int(s.get('canon_time_minutes', int(s.get('canon_day', 0)) * 1440 + 480))


def npc_at(memory, place):
    """Use the shared NPC location contract without requiring legacy `location`."""
    known = memory.get('location') or memory.get('last_known_location')
    return str(known or '').strip().casefold() == str(place or '').strip().casefold()


def definitions(s):
    if not offline_enabled():
        return []
    from simulation_integrity import canon_dependency_graph
    dependencies = {e['id']: e for e in canon_dependency_graph(s).get('events', [])}
    result = []
    for pack in PACKS.get(s.get('world'), []):
        event = next((e for e in timeline_for(s.get('world')).get('events', []) if e.get('title') == pack['title']), None)
        if not event or event.get('historical_only'):
            continue
        eid = f"day:{event.get('day', 0)}:{event['title']}"
        dep = dependencies.get(eid, {})
        due = int(dep.get('effective_day', event['day'])) * 1440 + 480
        result.append({**pack, 'event_id': eid, 'place': event['location'], 'due': due,
                       'opens': due - 120, 'depart': due - 1440,
                       'invalid': dep.get('status') in {'impossible', 'replaced'}})
    return result


def read(s):
    return obj(s.get('offline_world'))


def writable(s):
    root = s.setdefault('offline_world', {})
    if not isinstance(root, dict):
        root = s['offline_world'] = {}
    root.setdefault('version', 1)
    if not isinstance(root.get('appointments'), dict):
        root['appointments'] = {}
    return root


def appointment(s, pack):
    return obj(obj(read(s).get('appointments')).get(pack['key']))


def eligible(s, pack, before):
    if appointment(s, pack):
        return True
    anchor = s.get('calendar_anchor_day')
    return (pack['due'] > before and pack['event_id'] not in s.get('canon_events_fired', [])
            and (anchor is None or pack['due'] >= int(anchor) * 1440 + 480))


def settled(s, pack, row, status, message):
    row.update(status=status, resolved_minute=clock(s), summary=message)
    s.setdefault('canon_event_states', {})[pack['event_id']] = {
        'status': 'replaced' if status in {'intervened', 'cancelled'} else 'occurred',
        'reason': message, 'resolved_day': clock(s) // 1440,
    }
    fired = s.setdefault('canon_events_fired', [])
    if pack['event_id'] not in fired:
        fired.append(pack['event_id'])
    if status == 'intervened':
        s.setdefault('canon_divergences', []).append({'event_id': pack['event_id'], 'title': pack['title'], 'status': 'altered', 'reason': message})
    if pack.get('death') and status == 'occurred':
        for field in ('npc_memories', 'contacts'):
            record = obj(s.get(field)).get(pack['death'])
            if isinstance(record, dict):
                record.update(alive=False, status='dead')
        for record in s.get('companions', []):
            if isinstance(record, dict) and record.get('name') == pack['death']:
                record.update(alive=False, status='dead')


def tick(s, before, after):
    """Called before the ordinary canon backstop; returns owned event IDs + news."""
    owned, news = set(), []
    for pack in definitions(s):
        if not eligible(s, pack, before):
            continue
        rows = writable(s)['appointments']
        if not isinstance(rows.get(pack['key']), dict):
            rows[pack['key']] = {'status': 'scheduled'}
        row = rows[pack['key']]
        row.setdefault('status', 'scheduled')
        owned.add(pack['event_id'])
        # A rescue and the surrounding canon outcome are separate phases.
        # Preventing Duy's sacrifice ends that event; rescuing civilians does
        # not grant a free victory over Arlong or Aizen.
        if row.get('aftermath_due') is not None and after >= row['aftermath_due'] and not row.get('aftermath_resolved'):
            row['aftermath_resolved'] = True
            recorded = obj(obj(s.get('canon_event_states')).get(pack['event_id']))
            required = ['Monkey D. Luffy'] if pack['key'] == 'arlong' else ['Ichigo Kurosaki','Sosuke Aizen']
            changed = recorded.get('reason') != row.get('summary') or any(
                obj(obj(s.get('npc_memories')).get(name)).get('alive') is False for name in required)
            if not changed:
                message = pack['default']
                if pack['key'] == 'arlong':
                    liberate_arlong(s)
                news.append({'text': '[WORLD EVENT]\n'+message, 'tag':'system', 'canon_day':pack['due']//1440,
                             'major':False,'event_title':pack['title']+' — aftermath'})
        if row['status'] in {'occurred', 'intervened', 'cancelled'}:
            continue
        if pack['invalid']:
            settled(s, pack, row, 'cancelled', 'Earlier campaign changes prevented this scheduled encounter.')
            continue
        if row['status'] == 'combat':
            continue
        # A known death invalidates an appointment; it never resurrects an actor.
        if any(obj(obj(s.get('npc_memories')).get(name)).get('alive') is False for name in pack['actors']):
            settled(s, pack, row, 'cancelled', 'A required participant is no longer alive; this encounter cannot occur as originally scheduled.')
            continue
        row['status'] = 'available' if after >= pack['opens'] else 'traveling' if after >= pack['depart'] else 'scheduled'
        if after >= pack['due']:
            settled(s, pack, row, 'occurred', pack['default'])
            if pack['key'] == 'arlong':
                liberate_arlong(s)
            news.append({'text': '[WORLD EVENT]\n' + pack['default'], 'tag': 'system',
                         'canon_day': pack['due'] // 1440, 'major': False, 'event_title': pack['title']})
    return owned, news


def liberate_arlong(s):
    # No annexation and no overwrite of a campaign's intervening conqueror.
    for place in ('Arlong Park', 'Cocoyasi Village'):
        detail = obj(obj(s.get('location_details')).get(place))
        if detail.get('controlling_faction') == 'Arlong Pirates':
            detail.update(controlling_faction='Conomi Communities', controller_changed_turn=s.get('turn', 0))
            s.setdefault('factions', {}).setdefault('Conomi Communities', {})


def boundary(s, start, end, place):
    stops = []
    for pack in definitions(s):
        row = appointment(s, pack)
        if pack['invalid'] or row.get('status') in {'occurred', 'intervened', 'cancelled', 'combat'}:
            continue
        if eligible(s, pack, start) and place == pack['place'] and start < pack['opens'] <= end:
            stops.append((pack['opens'], pack['title'] + ' — intervention window'))
    return min(stops) if stops else None


def actions(s, place):
    rows = []
    for p in definitions(s):
        a = appointment(s, p)
        if (not p['invalid'] and eligible(s,p,clock(s)) and p['depart']-1440 <= clock(s) < p['depart']
                and place == p['origin'] and not a.get('route_report')):
            present = [name for name in p['actors'] if npc_at(obj(obj(s.get('npc_memories')).get(name)), place)
                       and obj(obj(s.get('npc_memories')).get(name)).get('alive') is not False]
            if present:
                rows.append({'id':'worldevent:report:'+p['key'], 'label':'Ask '+present[0]+' about the planned journey',
                    'category':'World','minutes':0,'description':'Record the route shared by this person here. Only eligible allies or group members can then appear as distant moving markers.'})
        if (not p['invalid'] and a.get('status') not in {'occurred', 'intervened', 'cancelled', 'combat'}
                and not a.get('attempted') and p['opens'] <= clock(s) < p['due'] and p['place'] == place
                and eligible(s, p, clock(s))):
            rows.append({'id': 'worldevent:' + p['key'], 'label': p['offer'], 'category': 'World',
                         'minutes': 0, 'description': p['brief'] + ' Starts a tactical protection encounter; victory is not guaranteed.'})
    return rows


def resolve(game, spec):
    s = game.state
    if not any(a['id'] == spec['id'] for a in actions(s, spec['place'])):
        raise ValueError('This intervention is no longer available at this location.')
    if spec['id'].startswith('worldevent:report:'):
        pack = next(p for p in definitions(s) if p['key'] == spec['id'].split(':')[-1])
        writable(s)['appointments'].setdefault(pack['key'], {'status':'scheduled'})['route_report'] = True
        for name in pack['actors']:
            memory = obj(obj(s.get('npc_memories')).get(name))
            if npc_at(memory, spec['place']) and memory.get('alive') is not False:
                memory['tracking_confirmed'] = True
        return 'The party shares its planned journey from '+pack['origin']+' to '+pack['place']+'. This is a route report, not knowledge of the event’s outcome.'
    pack = next(p for p in definitions(s) if 'worldevent:' + p['key'] == spec['id'])
    writable(s)['appointments'].setdefault(pack['key'], {}).update(status='combat', attempted=True)
    s['combat'] = {'active': True, 'tactical_enabled': True, 'cause': pack['brief'],
                   'enemy': {'name': pack['enemy'], 'power': pack['power'], 'hp': pack['power'] * 2 * pack['count'],
                             'hp_max': pack['power'] * 2 * pack['count'], 'is_group': True, 'group_size': pack['count']},
                   'adventure_objective': {'kind': 'protection', 'world_event': pack['key'],
                                           'target_label': {'duy': "Duy’s retreating team", 'arlong': 'the villagers', 'sokyoku': 'Rukia and Renji'}[pack['key']],
                                           'rounds_required': 4, 'rounds_survived': 0,
                                           'target_hp': 60, 'target_hp_max': 60, 'settled': False}, 'log': []}
    game.ensure_combat_numbers()
    from tactical_combat import ensure_board
    ensure_board(s)
    game.acknowledge_danger_scenario(pack['brief'])
    return pack['brief']


def combat_finished(game, outcome):
    s = game.state
    objective = obj(obj(s.get('combat')).get('adventure_objective'))
    if not objective.get('world_event') or objective.get('settled'):
        return
    pack = next((p for p in definitions(s) if p['key'] == objective['world_event']), None)
    if pack is None:
        raise ValueError('Missing authored world encounter definition.')
    objective['settled'] = True
    row = writable(s)['appointments'][pack['key']]
    success = outcome == 'objective_complete'
    message = pack['saved'] if success else 'Your intervention did not secure the retreat. The danger remains; the scheduled event has not been prevented.'
    if success:
        settled(s, pack, row, 'intervened', message)
        if pack['key'] in {'arlong','sokyoku'}:
            row['aftermath_due'] = pack['due']
    else:
        row['status'] = 'available'
    game.append(message, 'narrative', canon_day=s.get('canon_day'))


def visible_parties(s):
    """Local encounters are discoverable, distant schedules are not omniscience."""
    rows = []
    companions = {p.get('name') for p in s.get('companions', []) if isinstance(p, dict) and p.get('alive') is not False
                  and p.get('status', '').lower() not in {'dead', 'left', 'dismissed'}}
    groups = {a.get('faction') or a.get('name') for a in s.get('affiliations', []) if isinstance(a, dict)
              and a.get('status') not in {'left','dismissed','inactive'}}
    for group in groups:
        roster = obj(s.get('faction_rosters')).get(group, [])
        if isinstance(roster, list):
            companions.update(p if isinstance(p,str) else obj(p).get('name') for p in roster
                              if isinstance(p,str) or obj(p).get('alive') is not False and obj(p).get('status') not in {'dead','left','dismissed'})
    for p in definitions(s):
        a = appointment(s, p)
        if a.get('status') not in {'traveling', 'available', 'combat'}:
            continue
        local = a['status'] != 'traveling' and s.get('location') == p['place']
        route = route_position(s, p)
        for name in p['actors']:
            memory = obj(obj(s.get('npc_memories')).get(name))
            # Relationship alone is not a live tracker. An explicit tracking report
            # or a team member on a shared route is required away from the player.
            if not local and not (name in companions and memory.get('tracking_confirmed') is True):
                continue
            row = {'name': name, 'last_known_location': p['place'] if local else p['origin'],
                   'label': 'Witnessed event participant' if local else 'Confirmed party movement',
                   'goal': p['brief'] if local else 'Following the confirmed route.', 'event_id': p['key'],
                   'score': 0, 'knowledge': ['Present at this encounter'] if local else ['Confirmed travel report']}
            if not local and route:
                row.update(route)
            elif not local:
                continue  # Unknown route is not a straight line across an ocean/realm.
            rows.append(row)
    return rows


def route_position(s, pack):
    """Interpolate along legal map edges; never invent a portal or sea shortcut."""
    from simulation_integrity import build_travel_graph
    graph = build_travel_graph(s)
    nodes = {n['name']: n for n in graph['nodes']}
    origin, destination = pack['origin'], pack['place']
    if origin not in nodes or destination not in nodes:
        return None
    queue, seen = [(0, origin, [])], set()
    route = None
    while queue:
        cost, at, path = heapq.heappop(queue)
        if at in seen:
            continue
        seen.add(at)
        if at == destination:
            route = path
            break
        for edge in graph['edges'].get(at, []):
            if edge.get('requirement') or edge['to'] in seen:
                continue
            minutes = max(1, int(edge['minutes']))
            heapq.heappush(queue, (cost + minutes, edge['to'], path + [(at, edge['to'], minutes)]))
    if not route:
        return None
    duration = sum(e[2] for e in route)
    remaining = max(0, min(duration, (clock(s) - pack['depart']) / max(1, pack['opens'] - pack['depart']) * duration))
    for origin, destination, minutes in route:
        if remaining <= minutes:
            a, b = nodes[origin], nodes[destination]
            progress = remaining / minutes
            return {'x': a['x'] + (b['x'] - a['x']) * progress,
                    'y': a['y'] + (b['y'] - a['y']) * progress,
                    'route_from': origin, 'route_to': destination, 'route_progress': progress}
        remaining -= minutes
    return None
