"""Isolated, retry-safe local subsystem commits with non-sensitive diagnostics."""
import copy

def diagnostic(state, subsystem, code):
    root=state.setdefault('subsystem_health',{})
    if not isinstance(root,dict):root=state['subsystem_health']={}
    rows=root.setdefault('events',[])
    row={'subsystem':subsystem,'code':code,'turn':state.get('turn',0),'minute':state.get('canon_time_minutes',0)}
    if not rows or rows[-1]!=row: rows.append(row)
    del rows[:-60]

def run(state, name, callback):
    token=f"{state.get('campaign_id','')}:{state.get('turn',0)}:{state.get('canon_time_minutes',0)}"
    root=state.setdefault('subsystem_health',{})
    if not isinstance(root,dict):root=state['subsystem_health']={}
    systems=root.setdefault('systems',{})
    if systems.get(name,{}).get('completed_token')==token:return True
    local=copy.deepcopy(state)
    try:callback(local)
    except Exception as exc:
        # Never copy exception text, callback arguments, keys or private prose.
        code=type(exc).__name__ if type(exc) in (ValueError,TypeError,KeyError,AttributeError,OverflowError,IndexError) else 'SubsystemError'
        diagnostic(state,name,code)
        systems[name]={'status':'failed','failed_turn':state.get('turn',0),'code':code}
        return False
    for key in set(state)-set(local):state.pop(key,None)
    for key,value in local.items():
        if key not in state or state[key]!=value:state[key]=value
    state['subsystem_health'].setdefault('systems',{})[name]={'status':'ok','completed_token':token}
    return True

def public_view(state):
    root=state.get('subsystem_health') or {}
    return {'events':copy.deepcopy(root.get('events',[])),
            'systems':{name:{k:v for k,v in row.items() if k!='completed_token'} for name,row in root.get('systems',{}).items()}}
