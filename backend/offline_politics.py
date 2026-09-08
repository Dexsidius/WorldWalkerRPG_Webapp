"""Local support and scheduled civic petitions, independent of combat power.

An advisory mandate is deliberately not a transfer of a country or a village.
Military conquests continue to require military_resolution's explicit evidence.
"""
from runtime_mode import offline_enabled
from offline_world import obj, clock
import hashlib

GROUPS = {'Naruto': ('residents', 'local leaders', 'shinobi'),
          'One Piece': ('residents', 'merchants', 'crews'),
          'Bleach': ('district residents', 'district elders', 'patrols')}
WEEK = 10080


def read(s, place):
    return obj(obj(obj(s.get('offline_politics')).get('communities')).get(place))


def writable(s, place):
    root = s.setdefault('offline_politics', {'version': 1, 'communities': {}})
    return root.setdefault('communities', {}).setdefault(place, {'support': {}, 'last_work': {}, 'petitions': []})


def actions(s, place):
    if not offline_enabled() or s.get('world') not in GROUPS:
        return []
    from living_adventures import location_node, SETTLEMENTS
    if location_node(s, place).get('kind') not in SETTLEMENTS and not (s.get('world') == 'Bleach' and place == 'Seireitei'):
        return []
    from offline_life import wage, paid
    r = read(s, place)
    groups = GROUPS[s['world']]
    labels = ('Organize practical community relief', 'Meet local representatives', 'Coordinate public safety volunteers')
    rows = []
    for index, group in enumerate(groups):
        previous = obj(r.get('last_work')).get(group)
        support = int(obj(r.get('support')).get(group, 0))
        if support >= 60 or previous is not None and clock(s) - previous < WEEK:
            continue
        rows.append({'id': 'political:work:' + str(index), 'label': labels[index], 'category': 'Politics',
                     'minutes': 480, 'cost': round(wage(s) * (2 if index != 1 else 0), 2) if paid(s) else 0,
                     'currency': obj(s.get('currency')).get('name', 'currency'),
                     'description': f'{group.title()} support: {support}/60. Complete practical work to gain 10 support. This does not recruit troops or grant office. Repeat after seven days.',
                     'group': group})
    support = obj(r.get('support'))
    pending = any(p.get('status') == 'pending' for p in r.get('petitions', []) if isinstance(p, dict))
    if (not pending and not r.get('mandate') and min((int(support.get(g, 0)) for g in groups), default=0) >= 40
            and clock(s) >= int(r.get('retry_after', -10**12))):
        rows.append({'id': 'political:petition', 'label': 'Petition for a local advisory mandate', 'category': 'Politics',
                     'minutes': 60, 'description': 'Local representatives review the petition within seven days. A mandate allows civic representation, not ownership, national leadership or command of the army.'})
    occupation = obj(obj(obj(s.get('offline_politics')).get('occupations')).get(place))
    from politics import player_led_polities
    led = player_led_polities(s)
    if (occupation.get('controller') in led and occupation.get('status') == 'occupied'
            and r.get('mandate') and min((int(support.get(g, 0)) for g in groups), default=0) >= 50):
        for kind, label in [('council', 'local council'), ('protectorate', 'local protectorate')]:
            rows.append({'id': 'political:government:' + kind, 'label': 'Convene a ' + label,
                         'category': 'Politics', 'minutes': 480,
                         'description': 'Establish civil administration in the captured holding. Representatives review the charter after seven days. Only this holding changes government; the surrounding country is not annexed.',
                         'government': kind})
    return rows


def resolve(s, spec):
    place = spec['place']
    current = next((a for a in actions(s, place) if a['id'] == spec['id']), None)
    if not current:
        raise ValueError('This political activity is no longer available.')
    from systems import record_currency_transaction
    if current.get('cost'):
        record_currency_transaction(s, -current['cost'], current['label'], 'community_project', source='offline_politics')
    r = writable(s, place)
    if current.get('government'):
        occupation = s['offline_politics']['occupations'][place]
        occupation.update(status='charter_pending', government=current['government'], charter_due=clock(s)+WEEK)
        return f'You convene representatives at {place}. They will review the {current["government"]} charter within seven days. The holding remains under occupation until a government is established.'
    if current.get('group'):
        group = current['group']
        r['support'][group] = min(60, int(r['support'].get(group, 0)) + 10)
        r['last_work'][group] = clock(s)
        return f"At {place}, your completed work earns support among {group}: {r['support'][group]}/60. No office, troops or territory changed hands."
    r['petitions'].append({'status': 'pending', 'submitted': clock(s), 'due': clock(s) + WEEK})
    return f'Local representatives at {place} receive your petition. Their review is scheduled within seven days; no authority has been granted yet.'


def tick(s, before, after):
    if not offline_enabled() or s.get('world') not in GROUPS:
        return []
    news = []
    for place, r in obj(obj(s.get('offline_politics')).get('communities')).items():
        if not isinstance(r, dict):
            continue
        for petition in r.get('petitions', []):
            if not isinstance(petition, dict) or petition.get('status') != 'pending' or petition['due'] > after:
                continue
            # Explicit local restrictions determine the response, not a random
            # negative twist on every successful player action.
            detail = obj(obj(s.get('location_details')).get(place))
            occupied = (s.get('world') == 'One Piece' and place in {'Arlong Park', 'Cocoyasi Village'}
                        and after < 14 * 1440 + 480 and detail.get('controlling_faction', 'Arlong Pirates') == 'Arlong Pirates')
            blocked = detail.get('civic_assembly_forbidden') is True or occupied
            petition['status'] = 'refused' if blocked else 'accepted'
            petition['resolved'] = after
            if blocked:
                r['retry_after'] = after + WEEK
                reason = 'Arlong’s occupation does not recognize an independent civic mandate' if occupied else 'the established local ban on civic assembly is still in force'
                message = f'The petition at {place} cannot proceed: {reason}. Your community support is retained.'
            else:
                r['mandate'] = {'office': 'Community representative', 'scope': place, 'granted': petition['due']}
                message = f'The local representatives at {place} accept your petition. You may speak for the civic association as a community representative. This is not a transfer of government or territory.'
            news.append({'text': '[LOCAL DECISION]\n' + message, 'tag': 'system', 'canon_day': petition['due'] // 1440,
                         'major': False, 'event_title': 'Civic petition at ' + place})
    return news


def record_capture(s, faction, place, defender):
    """A resolved, evidence-backed military victory grants one local foothold.

    The stable claim ID prevents replay or repeat operations multiplying land.
    National sovereignty and Naruto's village/country split are left intact.
    """
    ident = 'occupation-' + hashlib.sha256(f'{s.get("world")}|{place}'.encode()).hexdigest()[:16]
    root = s.setdefault('offline_politics', {'version': 1, 'communities': {}})
    root.setdefault('occupations', {})[place] = {'controller': faction, 'previous_controller': defender,
        'claim_id': ident, 'status': 'occupied', 'captured': clock(s)}
    claims = s.setdefault('political_regions', [])
    claim = next((r for r in claims if isinstance(r, dict) and r.get('id') == ident), None)
    if claim is None:
        claim = {'id': ident, 'name': 'Foothold at ' + place, 'anchor': place, 'world': s.get('world'),
                 'scale': 'holding', 'hex_count': 1, 'status': 'active'}
        claims.append(claim)
    claim.update(controller=faction, controller_changed_turn=s.get('turn', 0))
    return f'{faction} secured a foothold at {place} from {defender}. Only the captured holding is occupied; the surrounding territory and government are unchanged.'


def tick_governments(s, after):
    if not offline_enabled():
        return []
    news=[]
    for place, occupation in obj(obj(s.get('offline_politics')).get('occupations')).items():
        if occupation.get('status') != 'charter_pending' or occupation.get('charter_due', after+1) > after:
            continue
        claim=next((r for r in s.get('political_regions', []) if isinstance(r,dict) and r.get('id')==occupation['claim_id']),None)
        if not claim or claim.get('controller') != occupation['controller'] or claim.get('status') != 'active':
            occupation['status']='lost'
            continue
        community=read(s,place)
        enough=min((int(obj(community.get('support')).get(g,0)) for g in GROUPS.get(s.get('world'),())),default=0)>=50
        if not enough:
            occupation['status']='occupied'
            continue
        occupation.update(status='governed', legitimacy='local charter', institutions=['civil administration','public accounts'], established=after)
        claim['name']=place+' '+('Council' if occupation['government']=='council' else 'Protectorate')
        message=f"The charter for {claim['name']} takes effect. Civil administration and public accounts are established in the captured holding. This does not confer sovereignty over the surrounding country."
        news.append({'text':'[LOCAL GOVERNMENT]\n'+message,'tag':'system','canon_day':occupation['charter_due']//1440,
                     'major':False,'event_title':claim['name']})
    return news


def view(s):
    place = s.get('location', '')
    r = read(s, place)
    return {'place': place, 'support': {g: int(obj(r.get('support')).get(g, 0)) for g in GROUPS.get(s.get('world'), ())},
            'mandate': obj(r.get('mandate')).get('office', ''),
            'pending': sum(p.get('status') == 'pending' for p in r.get('petitions', []) if isinstance(p, dict))}
