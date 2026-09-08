"""Persistent faction operations that turn existing faction clocks into visible world conflict."""
from __future__ import annotations
import copy, hashlib, re
from simulation_integrity import _map_nodes
TERMINAL={'completed','failed','cancelled','resolved'}

def _text(value,limit=300): return re.sub(r'\s+',' ',str(value or '')).strip()[:limit]
def _hash(*parts): return int(hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:8],16)
def _operation_id(faction,operation):
    explicit=_text(operation.get('id'),120)
    if explicit:return explicit
    seed=f"{faction}|{operation.get('type')}|{operation.get('objective')}|{operation.get('started_turn',0)}"
    return hashlib.sha256(seed.encode()).hexdigest()[:16]
def _existing_store(state): return state.get('world_conflict') if isinstance(state.get('world_conflict'),dict) else {}
def _store(state):
    r=state.setdefault('world_conflict',{})
    if not isinstance(r,dict):r=state['world_conflict']={}
    r.setdefault('version',2);r.setdefault('history',[]);r.setdefault('interventions',[]);return r

def visible(row):
    return isinstance(row,dict) and row.get('known_to_player') is not False and str(row.get('visibility','')).lower() not in {'hidden','secret','private'}

def elapsed_steps(state, key, elapsed):
    """One progress point per six campaign hours, independent of request count."""
    elapsed=max(0,int(elapsed or 0))
    now=int(state.get('canon_time_minutes',int(state.get('canon_day',0) or 0)*1440+480))
    ticks=_store(state).setdefault('ticks',{})
    row=ticks.setdefault(key,{'minute':now-elapsed,'remainder':0})
    minutes=min(elapsed,max(0,now-int(row.get('minute',now))))
    total=int(row.get('remainder',0))+minutes
    steps,remainder=divmod(total,360)
    row.update(minute=max(now,int(row.get('minute',now))),remainder=remainder)
    return steps

def _controller(state,place):
    row=(state.get('location_details') or {}).get(place,{}) if isinstance(state.get('location_details'),dict) else {}
    return str(row.get('controlling_faction') or '') if isinstance(row,dict) else ''
def _target(state,faction,clock,operation):
    explicit=_text(operation.get('target_location') or clock.get('target_location'))
    nodes=[n.get('name') for n in _map_nodes(state.get('world','Custom World')) if isinstance(n,dict) and n.get('name')]
    if explicit and explicit in nodes:return explicit
    blob=' '.join(_text(x) for x in (operation.get('objective'),clock.get('immediate_goal'),clock.get('goal')))
    for n in sorted(nodes,key=len,reverse=True):
        if n.casefold() in blob.casefold():return n
    rivals=[_text(x) for x in clock.get('rivals',[]) if _text(x)]
    for n in nodes:
        if _controller(state,n) in rivals:return n
    return ''  # Unknown targets must not become an attack on the first map node.
def _chance(clock,kind):
    resources=clock.get('resources') if isinstance(clock.get('resources'),dict) else {}
    key={'military':'capacity','economic':'logistics','intelligence':'intelligence','diplomatic':'influence','influence':'influence'}.get(kind,'capacity')
    return max(20,min(85,int(resources.get(key,50) or 50)))
def _history(state,row):
    root=_store(state);root['history'].append(copy.deepcopy(row));root['history']=root['history'][-160:]
    if row.get('summary') and visible(row):
        state.setdefault('background_world_feed',[]).append({'turn':state.get('turn',0),'canon_day':state.get('canon_day'),'summary':row['summary']})
        state['background_world_feed']=state['background_world_feed'][-200:]

def _military_result(state,faction,target,success):
    # Compatibility entry point. A preparation roll is never a conquest result.
    return f"{faction}'s operation at {target or 'an unconfirmed destination'} awaits resolution; control is unchanged."

def refresh(state,elapsed_minutes=0):
    root=_store(state); elapsed=max(0,int(elapsed_minutes or 0));
    for faction,clock in (state.get('faction_clocks') or {}).items():
        if not isinstance(clock,dict):continue
        if clock.get('status') in {'destroyed','defeated','cancelled','inactive'}:continue
        ops=clock.setdefault('operations',[])
        if not ops:
            # Existing faction clock becomes one operation rather than a parallel agenda.
            ops.append({'type':'influence','objective':clock.get('immediate_goal') or clock.get('goal') or f'Advance {faction}\'s current agenda','progress':int(clock.get('progress',0) or 0),'status':'active','started_turn':int(state.get('turn',0) or 0)})
        for op in ops:
            if not isinstance(op,dict):continue
            op.setdefault('id',_operation_id(faction,op));op.setdefault('type','influence');op.setdefault('target_location',_target(state,faction,clock,op));op.setdefault('status','active')
            if op.get('status')!='active':continue
            pace=elapsed_steps(state,'operation:'+str(faction)+':'+op['id'],elapsed)
            op['progress']=min(100,int(op.get('progress',0) or 0)+pace)
            if int(op.get('progress',0) or 0)<100:continue
            if op.get('type')=='military':
                op['status']='awaiting_resolution'
                op['resolution_requirements']='Resolve from established attackers, defenders, fortifications, access and supplies. Preparation alone changes no territory. Unknown opposition requires investigation or narrative resolution, not assumed victory.'
                continue
            chance=_chance(clock,op.get('type','influence'));success=(_hash(state.get('campaign_id'),op['id'])%100)<chance
            target=op.get('target_location') or _target(state,faction,clock,op);kind=op.get('type','influence');changes=[]
            if kind=='military':summary=_military_result(state,faction,target,success);changes.append(summary)
            elif success and kind=='economic':
                res=clock.setdefault('resources',{});res['logistics']=min(100,int(res.get('logistics',50) or 50)+8);summary=f"{faction}'s economic operation at {target or 'its current front'} succeeded: logistics improved."
            elif success and kind=='intelligence':
                clock.setdefault('known_intel',[]).append({'target':target,'turn':state.get('turn'),'result':'Useful intelligence gathered'});clock['known_intel']=clock['known_intel'][-12:];summary=f"{faction}'s intelligence operation at {target or 'its current front'} succeeded; useful intelligence was gathered."
            elif success and kind=='diplomatic':summary=f"{faction}'s diplomatic initiative at {target or 'its current front'} gained ground."
            elif success:summary=f"{faction}'s {kind} operation at {target or 'its current front'} gained influence."
            else:summary=f"{faction}'s {kind} operation at {target or 'its current front'} stalled: the operation met resistance and lost momentum."
            op['status']='completed' if success else 'failed';op['resolution']='success' if success else 'setback';op['recent_outcome']=summary;op['worldwalker_settled']=True
            row={'id':op['id'],'turn':state.get('turn'),'canon_day':state.get('canon_day'),'faction':faction,'kind':kind,'target':target,'success':success,'summary':summary,'changes':changes,'known_to_player':visible(clock) and visible(op)};_history(state,row);clock.setdefault('recent_outcomes',[]).append(row);clock['recent_outcomes']=clock['recent_outcomes'][-12:]
    return public_view(state)

def operations_at(state,place):
    out=[]
    for faction,clock in (state.get('faction_clocks') or {}).items():
        if not visible(clock):continue
        for op in clock.get('operations',[]) or []:
            if not visible(op) or op.get('status','active')!='active':continue
            target=op.get('target_location') or _target(state,faction,clock,op)
            if target!=place:continue
            out.append({'faction':faction,'id':_operation_id(faction,op),'type':op.get('type','influence'),'objective':op.get('objective') or clock.get('immediate_goal') or clock.get('goal'),'progress':int(op.get('progress',0) or 0),'target':target})
    return out[:8]
def actions(state,place):
    out=[]
    for op in operations_at(state,place):
        token=f"{op['faction']}:{op['id']}"
        out += [
          {'id':'conflict:investigate:'+token,'label':f"Investigate {op['faction']} activity",'minutes':90,'description':'Gather local intelligence without automatically helping either side.'},
          {'id':'conflict:assist:'+token,'label':f"Support {op['faction']} operation",'minutes':120,'description':'Commit time and influence to this operation; the operation still resolves from its own resources and opposition.'},
          {'id':'conflict:sabotage:'+token,'label':f"Disrupt {op['faction']} operation",'minutes':180,'description':'Attempt to slow the operation locally. This can create faction consequences.'},]
    return out[:12]
def resolve_intervention(state,action,elapsed):
    parts=str(action or '').split(':',3)
    if len(parts)<4 or parts[0]!='conflict':raise ValueError('Unknown faction intervention.')
    mode,faction,oid=parts[1],parts[2],parts[3];clock=(state.get('faction_clocks') or {}).get(faction)
    if not isinstance(clock,dict):raise ValueError('That faction operation no longer exists.')
    op=next((o for o in clock.get('operations',[]) if isinstance(o,dict) and _operation_id(faction,o)==oid),None)
    if not op or not visible(clock) or not visible(op) or op.get('status','active')!='active':raise ValueError('That faction operation is not available.')
    if mode=='assist':op['progress']=min(99,int(op.get('progress',0) or 0)+max(2,int(elapsed or 0)//30));summary=f"You materially supported {faction}'s operation."
    elif mode=='sabotage':
        op['progress']=max(0,int(op.get('progress',0) or 0)-max(2,int(elapsed or 0)//30));res=clock.setdefault('resources',{});res['capacity']=max(0,int(res.get('capacity',50) or 50)-8);summary=f"You disrupted {faction}'s operation."
    elif mode=='investigate':
        clock.setdefault('known_intel',[]).append({'target':op.get('target_location'),'turn':state.get('turn'),'result':op.get('objective') or clock.get('immediate_goal')});clock['known_intel']=clock['known_intel'][-12:];summary=f"You learned more about {faction}'s current operation."
    else:raise ValueError('Unknown faction intervention.')
    _store(state)['interventions'].append({'turn':state.get('turn'),'canon_day':state.get('canon_day'),'faction':faction,'operation_id':oid,'mode':mode,'summary':summary});_store(state)['interventions']=_store(state)['interventions'][-100:]
    return {'message':summary,'world_conflict':public_view(state)}
def public_view(state):
    operations=[]
    for faction,clock in (state.get('faction_clocks') or {}).items():
        if not visible(clock):continue
        for op in clock.get('operations',[]) or []:
            if not visible(op):continue
            operations.append({'faction':faction,'id':_operation_id(faction,op),'type':op.get('type','influence'),'objective':op.get('objective') or clock.get('immediate_goal'),'target':op.get('target_location') or _target(state,faction,clock,op),'progress':int(op.get('progress',0) or 0),'status':op.get('status','active'),'resolution':op.get('resolution',''),'recent_outcome':op.get('recent_outcome','')})
    root=_existing_store(state)
    allowed={(r['faction'],r['id']) for r in operations}
    history=[r for r in root.get('history',[]) if visible(r) and (r.get('faction'),r.get('id')) in allowed]
    return {'operations':operations[:40],'history':copy.deepcopy(history[-30:]),'interventions':copy.deepcopy(root.get('interventions',[])[-20:])}

def sanitize_public(state):
    """Use on an already-copied public snapshot, never on simulation state."""
    hidden_summaries={r.get('summary') for r in _existing_store(state).get('history',[]) if isinstance(r,dict) and not visible(r)}
    concealed={name for name,clock in (state.get('faction_clocks') or {}).items() if not visible(clock) or any(not visible(op) for op in clock.get('operations',[]))}
    state['world_conflict']=public_view(state)
    clocks={}
    for name,clock in (state.get('faction_clocks') or {}).items():
        if not visible(clock):continue
        ops=[op for op in clock.get('operations',[]) if visible(op)]
        # Parent goals and recent outcomes may repeat a concealed operation.
        clocks[name]=dict(clock,operations=ops) if len(ops)==len(clock.get('operations',[])) else {'name':name,'operations':ops}
    state['faction_clocks']=clocks
    state['background_world_feed']=[r for r in state.get('background_world_feed',[]) if not isinstance(r,dict) or (visible(r) and r.get('summary') not in hidden_summaries)]
    state['causality_ledger']=[r for r in state.get('causality_ledger',[]) if isinstance(r,dict) and visible(r) and r.get('actor') not in concealed]

def resolution_context(state):
    pending=[]
    for faction,clock in (state.get('faction_clocks') or {}).items():
        if not isinstance(clock,dict):continue
        for op in clock.get('operations',[]):
            if isinstance(op,dict) and op.get('status')=='awaiting_resolution':
                pending.append({'faction':faction,'id':op.get('id'),'objective':op.get('objective'),'target':op.get('target_location'),'resources':clock.get('resources',{}),'requirements':op.get('resolution_requirements')})
    return {'pending':pending[:8],'rule':'Military preparation is not victory. Resolve only when established forces, defenders, access and supplies support the outcome; otherwise leave awaiting_resolution. Return the operation status completed/failed and resolution evidence in faction_clocks through the normal state patch. Record actual ownership changes through the existing political/location fields; never infer them from a timer. Keep secret operations out of player prose until a credible information path exists.'}
def location_status(state,place):
    detail=(state.get('location_details') or {}).get(place,{}) if isinstance(state.get('location_details'),dict) else {}
    return {'controller':detail.get('controlling_faction','') if isinstance(detail,dict) else '', 'contested_by':copy.deepcopy(detail.get('contested_by',[]) if isinstance(detail,dict) else []),'conflict_pressure':copy.deepcopy(detail.get('conflict_pressure',{}) if isinstance(detail,dict) else {}),'fortification':int(detail.get('fortification',0) or 0) if isinstance(detail,dict) else 0,'operations':operations_at(state,place)}
