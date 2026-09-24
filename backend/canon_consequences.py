"""Small, authored continuations of confirmed canon interventions.

The chain is private simulation state. Only a scene the player witnesses or
participates in is presented as knowledge. These continuations preserve the
immediate rescue without assuming a war, government, or relationship changed.
"""

from runtime_mode import offline_enabled


FOLLOWUPS = {
    "Yahiko's death and Akatsuki's transformation": {
        'target': 'Yahiko', 'place': 'Amegakure',
        'opening': 'Yahiko survived the ambush. He is trying to reconnect with whoever escaped; the movement must decide what to do next.',
        'help': 'Help reunite the scattered relief teams',
        'help_result': 'You reconnect the relief teams and pass on the needs they reported. That gives Yahiko a practical next step; it does not settle Rain\'s politics.',
        'next': 'Yahiko continues the relief effort with available allies while reassessing the danger from Hanzō. The movement\'s future doctrine is no longer fixed by his death.',
        'goal': 'Regroup the original Akatsuki and protect Rain communities after the ambush.',
        'strategies': {
            'relief': ('Organize a civilian supply route', 'You help the group establish a local route for food and medicine. It is a practical foothold, not control of Rain.', 'Maintain the local relief route and assess community needs.'),
            'testimony': ('Collect witness accounts of the ambush', 'You record firsthand accounts from willing survivors. Yahiko can use the evidence, but Hanzō has not been overthrown.', 'Review the ambush testimony and decide whom to approach.'),
        },
    },
    "Ace's death": {
        'target': 'Portgas D. Ace', 'place': 'Marineford',
        'opening': 'Ace escaped the immediate fatal attack. The battle and Marine pursuit continue, and the retreating pirates need to account for their people.',
        'help': 'Help the retreating crew find a safe rendezvous',
        'help_result': 'You pass a viable rendezvous route to the retreating crew. Ace has a way to regroup; the war and the fate of Whitebeard are not decided by this task.',
        'next': 'Ace seeks surviving allies after Marineford. Luffy\'s training remains his own decision, not an automatic reaction to Ace\'s death.',
        'goal': 'Regroup with surviving allies after escaping Marineford.',
        'strategies': {
            'rendezvous': ('Coordinate a discreet crew rendezvous', 'You help the survivors agree on a meeting point they can reach. Ace still has to evade the continuing pursuit.', 'Reach the agreed rendezvous with surviving allies.'),
            'contacts': ('Prepare messages for known allies', 'You prepare names and safe channels for the survivors to use. No message is treated as delivered yet.', 'Choose a safe channel to contact known allies.'),
        },
    },
    'Renji and Byakuya come for Rukia': {
        'target': 'Rukia Kuchiki', 'place': 'Karakura Town',
        'opening': 'Rukia avoided the immediate detention. Soul Society\'s order still exists, and the officers involved must account for what happened.',
        'help': 'Record what you witnessed for a lawful review',
        'help_result': 'You preserve a firsthand account of Rukia\'s escape and the attempted detention. It can be given to an authorized officer; it does not erase the order.',
        'next': 'Rukia remains free for now. Soul Society must respond to the failed detention; an execution on the original timetable is not an established outcome.',
        'goal': 'Remain safe while the unresolved Soul Society order is addressed.',
        'strategies': {
            'shelter': ('Arrange a temporary refuge for Rukia', 'You identify a place where Rukia can recover without claiming that Soul Society abandoned its order.', 'Use the temporary refuge while assessing the next official move.'),
            'testimony': ('Prepare a formal eyewitness account', 'You write down what you witnessed during the attempted detention. It can be delivered later; no officer is assumed to have read it.', 'Decide which trustworthy officer should receive the eyewitness account.'),
        },
    },
}

# These replace only the precise original scene whose premise the rescue
# removed. They are not forecasts of who wins a new war or what a player does.
VARIANTS = {
    "Yahiko's death and Akatsuki's transformation": {
        "Jiraiya's death in Amegakure": "Jiraiya may still investigate Rain, but the original confrontation with a grief-driven Pain is no longer scheduled as written.",
        "Pain's Assault on Konoha": "Nagato's original assault is no longer a fixed outcome of Yahiko's death. Rain and Konoha can still come into conflict through later choices.",
        "Naruto vs. Pain": "The original duel cannot be assumed without the assault that produced it. Naruto and Nagato retain their own goals.",
    },
    "Ace's death": {
        "Luffy begins two years of training": "Rayleigh can still propose training, but Ace's death cannot be used as Luffy's motivation. Luffy's decision remains his own.",
    },
    'Renji and Byakuya come for Rukia': {
        'Rukia is sentenced to execution': "Rukia was not returned by this detention. The original accelerated execution is not established; Soul Society's order remains unresolved.",
        'Training with Urahara Kisuke': "Ichigo may still train with Urahara, but the original rescue preparation is no longer scheduled on the assumption that Rukia awaits execution.",
        'The push into Seireitei': "A rescue raid to stop Rukia's original execution is no longer automatic. Soul Society may still act on its unresolved order.",
        "Aizen's betrayal at Sokyoku Hill": "Without that execution, Aizen's original reveal at Sokyoku Hill is not scheduled as written. His independent plans remain unresolved.",
    },
}


def obj(value):
    return value if isinstance(value, dict) else {}


def read(state):
    return obj(obj(state.get('offline_world')).get('consequence_chains'))


def writable(state):
    root = state.setdefault('offline_world', {})
    if not isinstance(root, dict):
        root = state['offline_world'] = {}
    if not isinstance(root.get('consequence_chains'), dict):
        root['consequence_chains'] = {}
    return root['consequence_chains']


def record_rescue(state, plan, target, saved_minute=None):
    """Call only after a tactical objective confirmed this particular rescue."""
    authored = FOLLOWUPS.get(plan['title'])
    if not authored or authored['target'] != target:
        return None
    source = plan['event_id']
    store = writable(state)
    if source in store:
        return store[source]
    minute = int(saved_minute if saved_minute is not None else state.get('canon_time_minutes', 0))
    row = {'source_event_id': source, 'source_title': plan['title'],
           'target': target, 'place': authored['place'], 'saved_minute': minute,
           'opens': minute + 60, 'decision_opens': minute + 1440,
           'due': minute + 3 * 1440, 'stage': 'recovery',
           'status': 'waiting', 'assisted': False, 'observed': False,
           'history': []}
    store[source] = row
    # A witnessed rescue is a durable, source-ranked fact for the GM and
    # Advisor. Do not turn it into an automatic faction victory or friendship.
    ledger = state.setdefault('consequence_ledger', [])
    if not any(isinstance(item, dict) and item.get('source_event_id') == source
               and item.get('title') == target + ' survived' for item in ledger):
        ledger.append({
            'title': target + ' survived', 'outcome': target + ' escaped the immediate danger at '
            + authored['place'] + '. The wider conflict remains unresolved.',
            'source_event_id': source, 'turn': state.get('turn', 0), 'canon_day': minute // 1440,
        })
    intentions = state.setdefault('npc_intentions', {})
    if isinstance(intentions, dict):
        npc = intentions.setdefault(target, {})
        if isinstance(npc, dict) and not npc.get('goal'):
            npc.update(goal=authored['goal'], location=authored['place'], status='recovering')
    return row


def reconcile_old_rescues(state, plans):
    """Enroll only a completed, successful tactical rescue from an older save."""
    completed = obj(obj(state.get('offline_world')).get('plans'))
    for plan in plans:
        row = obj(completed.get(plan['key']))
        rescue = plan.get('rescue')
        if (plan['title'] in FOLLOWUPS and rescue and row.get('status') == 'intervened'
                and row.get('attempted') and 'reaches safety under your protection' in str(row.get('summary', ''))
                and plan['event_id'] not in read(state)):
            from offline_canon_plans import actor_unavailable
            if not actor_unavailable(state, rescue[0], allow_captive=True):
                record_rescue(state, plan, rescue[0], row.get('resolved_minute'))


def variant_for(state, title):
    for row in read(state).values():
        if not isinstance(row, dict):
            continue
        variant = VARIANTS.get(row.get('source_title'), {}).get(title)
        if variant:
            return variant + (' ' + row['resolution'] if row.get('strategy') and row.get('resolution') else '')
    return ''


def _live(state, row, authored):
    if not offline_enabled() or state.get('location') != authored['place']:
        return False
    if row.get('status') != 'available' or row.get('declined'):
        return False
    minute = int(state.get('canon_time_minutes', 0))
    return row['opens'] <= minute < row['due']


def _items(state):
    if not offline_enabled():
        return []
    return [(source, row, FOLLOWUPS[row.get('source_title')])
            for source, row in read(state).items()
            if isinstance(row, dict) and row.get('source_title') in FOLLOWUPS]


def tick(state, before, after):
    """Advance the alternate aftermath without broadcasting private schedules."""
    if not offline_enabled():
        return []
    for source, row, authored in _items(state):
        if row.get('status') in {'complete', 'cancelled'}:
            continue
        from offline_canon_plans import actor_unavailable
        if actor_unavailable(state, row['target']):
            row['status'] = 'cancelled'
            row['resolution'] = 'A later change made this follow-up impossible.'
            row['resolved_minute'] = after
            continue
        if after >= row['opens'] and row.get('status') == 'waiting':
            row['status'] = 'available'
        if after >= row['decision_opens'] and row.get('stage') == 'recovery':
            row['stage'] = 'decision'
        if after >= row['due'] and row.get('status') == 'available':
            row['status'] = 'complete'
            row['resolution'] = authored['next']
            row['resolved_minute'] = row['due']
            # The NPCs continue their own modest plan. Their specific later
            # victories, whereabouts and knowledge are not invented here.
            intention = obj(obj(state.get('npc_intentions')).get(row['target']))
            if intention.get('status') == 'recovering':
                intention['status'] = 'active'
    return []


def boundary(state, start, end, place):
    if not offline_enabled():
        return None
    stops = [(row['opens'], 'A changed-history follow-up is available')
             for _, row, authored in _items(state)
             if row.get('status') == 'waiting' and authored['place'] == place
             and start < row['opens'] <= end]
    stops.extend((row['decision_opens'], 'A changed-history decision is available')
                 for _, row, authored in _items(state)
                 if row.get('status') not in {'complete', 'cancelled'} and not row.get('declined')
                 and authored['place'] == place and start < row['decision_opens'] <= end)
    return min(stops) if stops else None


def actions(state, place):
    if not offline_enabled() or state.get('location') != place:
        return []
    out = []
    for source, row, authored in _items(state):
        if not _live(state, row, authored):
            continue
        prefix = 'worldevent:consequence:' + source + ':'
        minute = int(state.get('canon_time_minutes', 0))
        if row.get('stage') == 'recovery':
            if not row.get('assisted') and minute + 60 < row['decision_opens']:
                out.append({'id': prefix + 'help', 'label': authored['help'], 'minutes': 60,
                            'category': 'World', 'description': authored['opening'] + ' Takes one hour; no automatic victory or rank gain.'})
            if not row.get('observed') and minute + 15 < row['decision_opens']:
                out.append({'id': prefix + 'observe', 'label': 'Speak with the survivors', 'minutes': 15,
                            'category': 'World', 'description': authored['opening'] + ' Takes fifteen minutes.'})
        elif minute + 60 < row['due']:
            for verb, (label, result, _) in authored['strategies'].items():
                out.append({'id': prefix + verb, 'label': label, 'minutes': 60,
                            'category': 'World', 'description': result + ' Takes one hour.'})
        out.append({'id': prefix + 'leave', 'label': 'Leave them to choose their next step', 'minutes': 0,
                    'category': 'World', 'description': 'No penalty. The people involved continue their own plans.'})
    return out


def view(state, place):
    if not offline_enabled() or state.get('location') != place:
        return []
    out = []
    for source, row, authored in _items(state):
        if not _live(state, row, authored):
            continue
        out.append({'title': row['target'] + ' — changed history', 'kind': 'Alternate aftermath',
                    'authorship': 'Authored continuation of a confirmed rescue', 'stage': 'decision',
                    'narrative': authored['opening'] if row.get('stage') == 'recovery' else authored['next'],
                    'place': place, 'person': row['target'],
                    'basis': 'You protected this person', 'prepared': bool(row.get('assisted')),
                    'prefix': 'worldevent:consequence:' + source + ':', 'key': source,
                    'changes': [authored['help_result']] if row.get('assisted') else [],
                    'history': row.get('history', [])})
    return out


def resolve(state, spec):
    action = spec['id']
    choice = next((a for a in actions(state, spec['place']) if a['id'] == action), None)
    if not choice:
        raise ValueError('This changed-history follow-up is no longer available here.')
    source = action[len('worldevent:consequence:'):].rsplit(':', 1)[0]
    verb = action.rsplit(':', 1)[1]
    row = writable(state)[source]
    authored = FOLLOWUPS[row['source_title']]
    if verb == 'help':
        row['assisted'] = True
        row['observed'] = True
        message = authored['help_result']
        state.setdefault('consequence_ledger', []).append({
            'title': choice['label'], 'outcome': message, 'source_event_id': source,
            'turn': state.get('turn', 0), 'canon_day': int(state.get('canon_day', 0)),
        })
    elif verb == 'observe':
        row['observed'] = True
        message = authored['opening']
    elif verb in authored['strategies']:
        _, message, next_action = authored['strategies'][verb]
        row.update(status='complete', strategy=verb, resolution=message,
                   resolved_minute=int(state.get('canon_time_minutes', 0)))
        intention = obj(obj(state.get('npc_intentions')).get(row['target']))
        if intention.get('goal') == authored['goal']:
            intention.update(next_action=next_action, status='active')
        state.setdefault('consequence_ledger', []).append({
            'title': choice['label'], 'outcome': message, 'source_event_id': source,
            'turn': state.get('turn', 0), 'canon_day': int(state.get('canon_day', 0)),
        })
    else:
        row['declined'] = True
        message = 'You leave the decision to those involved. ' + authored['next']
    row.setdefault('history', []).append({'title': choice['label'], 'text': message,
                                          'minute': int(state.get('canon_time_minutes', 0))})
    return message


def ai_facts(state, query='', limit=4):
    """Compact confirmed facts, never private appointment timing or routes."""
    terms = str(query or '').casefold()
    rows = [row for row in read(state).values() if isinstance(row, dict)]
    if terms:
        rows.sort(key=lambda row: (str(row.get('target', '')).casefold() not in terms,
                                   -int(row.get('saved_minute', 0))))
    else:
        rows.sort(key=lambda row: -int(row.get('saved_minute', 0)))
    return [{'person': row['target'], 'fact': row['target'] + ' survived the original '
             + row['source_title'] + ' encounter in this campaign. Original death or detention must not be assumed.',
             'source_event_id': row['source_event_id']}
            for row in rows[:limit] if isinstance(row, dict) and row.get('source_title') in FOLLOWUPS]
