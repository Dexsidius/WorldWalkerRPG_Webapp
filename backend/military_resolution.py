"""Shared evidence-based resolver for prepared faction operations and old clocks."""
import hashlib
import math

RULE = ('Military preparation is not victory. Supply military_evidence on the operation/legacy clock only from established campaign facts: '
        '{basis: factual explanation, attacker_strength: nonnegative fighting strength, defender_strength: nonnegative garrison strength, '
        'fortification_multiplier: number >=1, access_confirmed:true, supplies_confirmed:true}. '
        'Name the defender with opponent. Unknown forces, access, supplies or defenses leave the operation awaiting_resolution. '
        'Do not replace these missing facts with default power, player-scaled enemies, a random conquest or direct territory patches. '
        'The local resolver compares attack with garrison times fortification, records the outcome once, and applies supported control changes. '
        'Do not claim the destruction of a whole faction from one local defeat. Keep hidden operations out of player prose.')

def obj(v): return v if isinstance(v,dict) else {}

def numeric(v):
    if isinstance(v,bool): return None
    try:
        n=float(v)
        return n if math.isfinite(n) and n>=0 else None
    except (TypeError,ValueError): return None

def resolve_operation(state, faction, clock, operation):
    from world_conflict import visible, _history, _store
    root=_store(state); settled=root.setdefault('military_results',{})
    ident=str(operation.get('id','')); key=f'{faction}:{ident}'
    if key in settled:
        operation.update(settled[key]); return None
    operation['status']='awaiting_resolution'
    operation['resolution_requirements']=RULE
    target=str(operation.get('target_location') or clock.get('contested_location') or '').strip()
    detail=obj(obj(state.get('location_details')).get(target))
    defender=str(operation.get('opponent') or clock.get('opponent') or detail.get('controlling_faction') or '').strip()
    known=set(obj(state.get('factions')))|set(obj(state.get('faction_clocks')))
    evidence=obj(operation.get('military_evidence') or clock.get('military_evidence'))
    attack=numeric(evidence.get('attacker_strength')); defense=numeric(evidence.get('defender_strength'))
    fort=numeric(evidence.get('fortification_multiplier'))
    blockers=[]
    if not ident or not target or not detail: blockers.append('location and defenses are not established')
    if faction not in known or defender not in known or defender==faction: blockers.append('both belligerents must be established')
    if detail.get('controlling_faction') != defender: blockers.append('defender does not match current control')
    if not isinstance(evidence.get('basis'),str) or not evidence['basis'].strip(): blockers.append('missing military evidence')
    if attack is None or attack<=0 or defense is None or fort is None or fort<1: blockers.append('forces and fortifications need explicit estimates')
    if evidence.get('access_confirmed') is not True or evidence.get('supplies_confirmed') is not True: blockers.append('access and supplies are not confirmed')
    # Known local defense records override optimistic proposed estimates.
    recorded=numeric(detail.get('defender_strength',detail.get('defender_power')))
    if recorded is not None and defense is not None: defense=max(defense,recorded)
    recorded_fort=numeric(detail.get('fortification_multiplier'))
    if recorded_fort is not None and fort is not None: fort=max(fort,recorded_fort)
    elif numeric(detail.get('fortification')) not in (None,0) and not evidence.get('fortification_basis'):
        blockers.append('explain how recorded fortifications are represented')
    if blockers:
        operation['blocked_reason']='; '.join(blockers)
        return None
    success=attack>defense*fort
    operation.pop('blocked_reason',None)
    operation.update(status='completed' if success else 'failed',resolution='success' if success else 'held',worldwalker_settled=True)
    if success:
        detail['controlling_faction']=faction
        detail['controller_changed_turn']=int(state.get('turn',0))
    summary=(f'{faction} took control of {target} from {defender}.' if success else f'{defender} held {target} against {faction}; control is unchanged.')
    operation['recent_outcome']=summary
    settled[key]={k:operation[k] for k in ('status','resolution','worldwalker_settled','recent_outcome')}
    disclosed=visible(clock) and visible(operation)
    _history(state,{'id':ident,'faction':faction,'target':target,'kind':'military','success':success,'summary':summary,
                    'known_to_player':disclosed,'turn':state.get('turn'),'canon_day':state.get('canon_day')})
    return {'type':'world','conflict':True,'faction':faction,'message':summary} if disclosed else None

def resolve_legacy(state, faction, clock, opponent):
    operation=clock.get('military_operation')
    if not isinstance(operation,dict):
        seed=f"{state.get('campaign_id')}|{faction}|{opponent}|{clock.get('contested_location')}|{state.get('turn',0)}"
        operation=clock['military_operation']={'id':'legacy-'+hashlib.sha256(seed.encode()).hexdigest()[:20],
            'type':'military','opponent':opponent,'target_location':clock.get('contested_location'),
            'objective':clock.get('immediate_goal') or clock.get('goal'),'progress':100}
    result=resolve_operation(state,faction,clock,operation)
    if operation.get('status') in {'completed','failed'}:
        clock.update(status='active',progress=0,opponent='',contested_location='',proposed=False)
        clock.pop('military_operation',None);clock.pop('military_evidence',None)
    else: clock['status']='awaiting_resolution'
    return result
