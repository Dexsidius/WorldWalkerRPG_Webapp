"""Shared, deterministic encounter director over confirmed adventure actions.

No model calls, wall-clock timers, substring parsing of story text, read-time
save mutation or client-supplied effects. All choices resolve through the
existing signed activity transaction. Only the current scene is public.
"""
import copy
import hashlib
from encounter_content import catalog

def obj(v): return v if isinstance(v,dict) else {}
def seq(v): return v if isinstance(v,list) else []
def minute(s): return int(s.get('canon_time_minutes',int(s.get('canon_day',0))*1440+480))
def read(s): return obj(obj(s.get('adventures')).get('encounters'))
def writable(s):
    from living_adventures import writable as adventure_store
    root=adventure_store(s).setdefault('encounters',{})
    if not isinstance(root,dict):raise ValueError('Encounter history needs repair before it can be changed.')
    for name in ('signals','resolved'):
        if not isinstance(root.setdefault(name,{}),dict):raise ValueError('Encounter history needs repair before it can be changed.')
    root.setdefault('version',1)
    return root

def signal_for(action):
    if action.startswith(('train:','path:')):return 'training'
    if action in {'scout','prepare','journey:arrived'}:return 'exploration'
    if action.startswith(('offline:work:','craft:','purchase:','property:')):return 'work'
    if action.startswith(('talk:','offline:bond:','offline:meet:','offline:trial:','offline:recruit:','offline:promise:')):return 'social'
    if action.startswith(('political:work:','political:government:','offline:story:')):return 'community'
    if action=='mission:completed':return 'investigation'
    return None

def record(s,action,place):
    """Only called for fully completed, committed actions, never a quote/partial."""
    family=signal_for(action)
    if not family:return
    root=writable(s);key=place+'|'+family;previous=obj(root['signals'].get(key))
    root['signals'][key]={'count':min(20,int(previous.get('count',0))+1),'minute':minute(s),'place':place,'family':family}
    # Bounded recent evidence; authored completion IDs stay permanently deduped.
    if len(root['signals'])>180:
        oldest=min(root['signals'],key=lambda k:root['signals'][k]['minute']);root['signals'].pop(oldest)

def evidence(s,p,place):
    family=p['family'];r=read(s);signals=obj(r.get('signals'));history=obj(signals.get(place+'|'+family))
    if int(history.get('count',0)) >= (1 if family=='investigation' else 2):
        return {'training':'Repeated local training','exploration':'Completed local surveys or journeys','work':'Repeated local work, trade or production',
                'social':'Time spent with local people','community':'Completed local community work','investigation':'A completed local assignment'}[family]
    # Conservative old-save support from structured records, never invented action history.
    if family=='work' and any(p.get('location')==place for p in seq(obj(s.get('property_economy')).get('properties')) if isinstance(p,dict)):
        return 'An established property here'
    if family=='social':
        from living_adventures import companions_here
        if companions_here(s,place):return 'A companion currently with you here'
    if family=='exploration' and sum(1 for h in seq(s.get('travel_history')) if isinstance(h,dict) and h.get('completed') and h.get('destination')==place)>=2:
        return 'Recorded journeys to this location'
    if family in {'community','investigation'}:
        completed=[x for x in obj(obj(s.get('adventures')).get('resolved')).values() if isinstance(x,dict) and x.get('origin')==place and x.get('status')=='completed']
        if completed:return 'A completed assignment for this community'
    return ''

def local_allowed(s,place):
    from living_adventures import location_node,SETTLEMENTS
    if location_node(s)['name']!=place:return False
    if not s.get('alive',True) or int(s.get('hp',1))<=0:return False
    # These first authored packs concern accessible settlements, not remote
    # enemy strongholds or unknown points invented by the narrator.
    node=location_node(s,place)
    if node.get('kind') not in SETTLEMENTS:return False
    if s.get('world')=='Bleach' and any(x in place.casefold() for x in ('hueco','las noches','hell','dangai','royal')):return False
    return True

def participant_available(s,row):
    name=row.get('person')
    memory=obj(obj(s.get('npc_memories')).get(name))
    location=memory.get('location') or memory.get('last_known_location')
    return memory.get('alive') is not False and str(memory.get('status','')).lower() not in {'dead','deceased','missing','hostile','imprisoned','away','left'} and (not location or location==row.get('place'))

def active_pack(s):
    row=obj(read(s).get('active'))
    p=next((p for p in catalog(s.get('world')) if p['id']==row.get('id')),None)
    return p,row

def offers(s,place):
    if not local_allowed(s,place) or obj(read(s).get('active')):return []
    if obj(s.get('combat')).get('active'):return []
    root=read(s)
    if minute(s)<int(root.get('next_offer_minute',-10**12)):return []
    rows=[]
    for p in catalog(s.get('world')):
        if p['id'] in obj(root.get('resolved')):continue
        if not participant_available(s,{'person':p['author']+' of '+place,'place':place}):continue
        why=evidence(s,p,place)
        if why:rows.append({**p,'basis':why})
    # Stable choice, not rerolled by reopening a menu. Show at most two leads.
    rows.sort(key=lambda p:hashlib.sha256((str(s.get('campaign_id'))+place+p['id']).encode()).hexdigest())
    return rows[:2]

def action(id,label,minutes,description,**extra):
    return dict(id='encounter:'+id,label=label,minutes=minutes,description=description,category='Encounters',**extra)

def actions(s,place):
    if not local_allowed(s,place) or obj(s.get('combat')).get('active'):return []
    p,r=active_pack(s)
    if r:
        if not p or r.get('place')!=place:return []
        rows=[action('leave','Leave this encounter',0,'Close this story without extra penalties or unearned rewards.')]
        if r.get('stage')=='aftermath':
            return [action('close','Continue your campaign',0,'Archive this outcome. Your established changes remain in the campaign.')]
        if r.get('stage')=='combat':return []
        if not participant_available(s,r):return rows
        if r.get('stage')=='opening':
            rows.insert(0,action('investigate','Look into the details',30,'Verify the account with the person present before choosing an approach.'))
            rows.insert(1,action('direct',p['direct_label'],60 if p.get('enemy') else 45,
                'Starts a tactical protection encounter. Hold the withdrawal for four rounds; success is not guaranteed.' if p.get('enemy') else 'Take the straightforward approach without further investigation.',encounter_id=p['id'],encounter_stage='opening'))
        elif r.get('stage')=='decision':
            rows.insert(0,action('prepared',p['prepared_label'],60,'Use the verified information. '+('Submit a report; this does not defeat the threat.' if p.get('enemy') else 'The result is recorded locally.'),encounter_id=p['id'],encounter_stage='decision'))
            rows.insert(1,action('direct',p['direct_label'],60 if p.get('enemy') else 45,'Starts a tactical protection encounter; no automatic victory.' if p.get('enemy') else 'Choose the simpler approach. No unrelated punishment.',encounter_id=p['id'],encounter_stage='decision'))
        # Bind every ticket to a particular story and stage, including exits.
        return [{**a,'encounter_id':p['id'],'encounter_stage':r.get('stage')} for a in rows]
    return [action('begin:'+p['family'],'Explore: '+p['title'],15,p['invitation'],encounter_id=p['id'],basis=p['basis']) for p in offers(s,place)]

def view(s,place):
    if not local_allowed(s,place):return {'offers':[]}
    p,r=active_pack(s)
    if not p or r.get('place')!=place:return {'offers':[{'title':p['title'],'basis':p['basis'],'description':p['invitation'],'family':p['family'],'action':'encounter:begin:'+p['family']} for p in offers(s,place)]}
    stage=r.get('stage','opening')
    narrative=r.get('summary') if stage=='aftermath' else p['finding'] if stage=='decision' else p['invitation']
    return {'offers':[], 'active':{'title':p['title'],'kind':'Major investigation' if p.get('enemy') else 'Local encounter','authorship':'Original Worldwalker story',
        'stage':stage,'place':place,'person':r.get('person'),'basis':r.get('basis'),'narrative':narrative,
        'available':participant_available(s,r),'changes':copy.deepcopy(seq(r.get('changes'))),
        'history':copy.deepcopy(seq(r.get('history')))[-8:]}}

def validate(s,spec):
    """Used both before and after elapsed time, and when resuming an interruption."""
    matches=actions(s,spec['place'])
    if not any(a['id']==spec['id'] and a.get('encounter_id')==spec.get('encounter_id') and a.get('encounter_stage')==spec.get('encounter_stage') for a in matches):
        raise ValueError('This encounter changed. Cancel the unfinished action or review its current choices.')

def remember(game,message,title):
    game.append(title+'\n\n'+message,'narrative',canon_day=game.state.get('canon_day'),detail={'encounter':True})

def finish(game,p,r,method,message,benefit=None):
    s=game.state;root=writable(s)
    if p['id'] in root['resolved']:return
    changes=[];place=r['place'];name=r['person']
    if benefit=='contact':
        local=s.setdefault('location_details',{}).setdefault(place,{})
        contacts=local.setdefault('adventure_contacts',[])
        if name not in contacts:contacts.append(name)
        memory=obj(obj(s.get('npc_memories')).get(name))
        memory['public_goal']='Exchange verified local route reports.'
        changes.append('Local reporting contact established. Field preparation here lasts three days.')
    elif benefit=='shelter':
        local=s.setdefault('location_details',{}).setdefault(place,{})
        local['adventure_shelter']=True
        services=local.setdefault('services',[])
        if 'Community rest point' not in services:services.append('Community rest point')
        changes.append('Public rest point opened. Ordinary recovery here improves by 25%; special injuries are unchanged.')
    elif benefit=='preparation':
        s.setdefault('adventures',{})['preparation']={'origin':place,'expires':minute(s)+4320,'prepared_minute':minute(s)}
        changes.append('Verified field preparation is available for three days. Travel still requires a mapped, accessible route.')
    r.update(stage='aftermath',summary=message,changes=changes,method=method)
    r.setdefault('history',[]).append({'title':'Outcome','text':message})
    root['resolved'][p['id']]={'place':place,'minute':minute(s),'method':method,'summary':message,'changes':changes}
    root['next_offer_minute']=minute(s)+1440
    remember(game,message+('\n\n'+' '.join(changes) if changes else ''),p['title'])
    from living_adventures import writable as adventure_store
    ad=adventure_store(s);entry=game.story_log[-1]
    ad.setdefault('aftermath',[]).append({'id':p['id'],'location':place,'title':p['title'],'description':message,'changes':changes,
        'method':method,'success':bool(benefit),'canon_day':s.get('canon_day'),'story_id':entry['id'],'world_time':s.get('world_time')})
    ad['aftermath']=ad['aftermath'][-100:]

def resolve(game,spec):
    s=game.state;validate(s,spec);root=writable(s);id=spec['id']
    if id.startswith('encounter:begin:'):
        p=next(p for p in offers(s,spec['place']) if p['id']==spec['encounter_id'])
        name=p['author']+' of '+spec['place']
        existing=obj(obj(s.get('npc_memories')).get(name))
        if existing and (existing.get('alive') is False or existing.get('last_known_location') not in {None,spec['place']}):
            raise ValueError('The local contact is no longer available here.')
        s.setdefault('npc_memories',{}).setdefault(name,{'status':'active','alive':True,'last_known_location':spec['place'],'public_goal':'Discuss '+p['title']+'.','original_encounter_contact':True})
        root['active']={'id':p['id'],'stage':'opening','place':spec['place'],'person':name,'basis':p['basis'],
                        'history':[{'title':'The invitation','text':p['invitation']}]}
        remember(game,p['invitation'],p['title']);return
    p,r=active_pack(s)
    if id=='encounter:close':root.pop('active',None);return
    if id=='encounter:leave':
        finish(game,p,r,'declined','You excuse yourself and return to your own plans. The participants continue without your involvement.');return
    if id=='encounter:investigate':
        r['stage']='decision';r['history'].append({'title':'What you verified','text':p['finding']});remember(game,p['finding'],p['title']);return
    if id=='encounter:direct' and p.get('enemy'):
        r['stage']='combat';s['combat']={'active':True,'tactical_enabled':True,'cause':p['invitation'],
            'enemy':{'name':p['enemy'],'power':p['power'],'hp':p['power']*4,'hp_max':p['power']*4,'is_group':True,'group_size':2},
            'adventure_objective':{'kind':'protection','encounter_id':p['id'],'target_label':'the withdrawing relief group','rounds_required':4,'rounds_survived':0,'target_hp':60,'target_hp_max':60,'settled':False},'log':[]}
        game.ensure_combat_numbers()
        from tactical_combat import ensure_board
        ensure_board(s);game.acknowledge_danger_scenario(p['invitation'])
        remember(game,'Protect the withdrawal for four rounds. The group’s survival, not defeating every opponent, is the objective.',p['title']);return
    prepared=id=='encounter:prepared'
    finish(game,p,r,'prepared' if prepared else 'direct',p['prepared_result'] if prepared else p['direct_result'],
        'shelter' if prepared and p['family']=='community' else 'contact' if prepared or p['family']=='community' else 'preparation')

def combat_finished(game,outcome):
    s=game.state;o=obj(obj(s.get('combat')).get('adventure_objective'));p,r=active_pack(s)
    if not p or r.get('stage')!='combat' or o.get('encounter_id')!=p['id'] or o.get('settled'):return
    o['settled']=True
    if outcome=='objective_complete':finish(game,p,r,'protected',p['direct_result'],'contact')
    else:finish(game,p,r,'withdrawal_unsecured','Your attempt did not secure the relief group’s withdrawal. Its safety remains unconfirmed. No success reward is granted.')

def ai_summary(s):
    """Only observed facts, never future branches, eligibility counters or rewards."""
    p,r=active_pack(s)
    return {} if not p else {'title':p['title'],'location':r.get('place'),'stage':r.get('stage'),
        'observed':[h['text'] for h in seq(r.get('history')) if isinstance(h,dict) and h.get('text')][-4:],
        'established_changes':seq(r.get('changes')),
        'rule':'Preserve these committed facts. Freeform proposals do not themselves complete a local encounter or grant its rewards.'}
