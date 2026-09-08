"""No model calls: scheduled history, intervention race and visibility contracts."""
import copy
import pytest
import runtime_mode
from offline_world import definitions, tick, actions, visible_parties, boundary, combat_finished
from test_reliability_update import session, state
from test_living_adventures import local


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(runtime_mode, 'MODE', 'offline')


def setup(world='Naruto'):
    s = state(world)
    p = definitions(s)[0]
    s.update(canon_time_minutes=p['depart']-60, canon_day=(p['depart']-60)//1440,
             calendar_anchor_day=(p['depart']-60)//1440, canon_events_fired=[], canon_divergences=[],
             location=p['place'], npc_memories={}, contacts={})
    return s, p


@pytest.mark.parametrize('world', ['Naruto', 'One Piece', 'Bleach'])
def test_default_once_and_read_purity(world):
    s,p=setup(world)
    before=copy.deepcopy(s)
    assert actions(s,p['place'])==[]
    assert visible_parties(s)==[]
    assert s==before
    owned,news=tick(s,s['canon_time_minutes'],p['due']+1)
    assert p['event_id'] in owned and len(news)==1
    assert tick(s,p['due']+1,p['due']+999)[1]==[]
    assert s['canon_events_fired'].count(p['event_id'])==1


def test_existing_history_is_not_replayed():
    s,p=setup()
    s['canon_time_minutes']=p['due']+100
    assert tick(s,p['due']+100,p['due']+200)==(set(),[])


def test_local_stop_and_hidden_distant_participants():
    s,p=setup()
    start=s['canon_time_minutes']
    assert boundary(s,start,p['due']+10,p['place'])[0]==p['opens']
    assert boundary(s,start,p['due']+10,'Sunagakure') is None
    tick(s,start,p['opens']);s['canon_time_minutes']=p['opens']
    assert len(visible_parties(s))==4
    s['location']='Sunagakure'
    assert visible_parties(s)==[]


def test_dead_actor_does_not_respawn():
    s,p=setup();s['npc_memories']={'Might Duy':{'alive':False}}
    tick(s,s['canon_time_minutes'],p['opens'])
    s['canon_time_minutes']=p['opens']
    assert actions(s,p['place'])==[] and visible_parties(s)==[]


@pytest.mark.parametrize('world',['Naruto','One Piece','Bleach'])
def test_real_transaction_starts_encounter_and_resolves_once(session,world):
    _,game,client=session;game.state,p=setup(world)
    tick(game.state,game.state['canon_time_minutes'],p['opens'])
    game.state['canon_time_minutes']=p['opens'];game.state['canon_day']=p['opens']//1440
    result=local(client,'worldevent:'+p['key'],p['place'])
    assert game.state['combat']['active']
    assert game.state['combat']['adventure_objective']['world_event']==p['key']
    combat_finished(game,'objective_complete')
    saved=copy.deepcopy(game.state['canon_divergences'])
    combat_finished(game,'objective_complete')
    assert game.state['canon_divergences']==saved
    assert tick(game.state,p['opens'],p['due']+60)[1]==[]
    assert game.state['offline_world']['appointments'][p['key']]['status']=='intervened'


def test_main_mode_unchanged(monkeypatch):
    s,p=setup();monkeypatch.setattr(runtime_mode,'MODE','main')
    before=copy.deepcopy(s)
    assert tick(s,p['depart'],p['due'])==(set(),[])
    assert s==before


def test_failed_intervention_does_not_kill_duy_early(session):
    _,game,client=session;game.state,p=setup()
    tick(game.state,game.state['canon_time_minutes'],p['opens'])
    game.state['canon_time_minutes']=p['opens']
    local(client,'worldevent:'+p['key'],p['place'])
    combat_finished(game,'fled')
    assert p['event_id'] not in game.state['canon_events_fired']
    assert actions(game.state,p['place'])==[]
    assert len(tick(game.state,p['opens'],p['due'])[1])==1


def test_remote_route_requires_explicit_tracking():
    s,p=setup();start=s['canon_time_minutes']
    halfway=(p['depart']+p['opens'])//2
    tick(s,start,halfway);s['canon_time_minutes']=halfway;s['location']='Sunagakure'
    s['companions']=[{'name':'Might Duy','status':'active'}]
    assert visible_parties(s)==[]
    s['npc_memories']={'Might Duy':{'tracking_confirmed':True}}
    rows=visible_parties(s)
    assert len(rows)==1 and 0<rows[0]['route_progress']<1


@pytest.mark.parametrize('world,place',[('Naruto','Konohagakure'),('One Piece','Cocoyasi Village'),('Bleach','Seireitei')])
def test_civic_work_and_scheduled_petition(session,world,place):
    from offline_politics import actions as offers, tick as decision_tick, GROUPS, WEEK
    _,game,client=session;game.state=state(world);s=game.state
    s.update(location=place,canon_time_minutes=20*1440,canon_day=20,currency={'name':'Test','amount':100000})
    before=copy.deepcopy(s);assert len(offers(s,place))==3;assert s==before
    local(client,'political:work:0',place)
    r=s['offline_politics']['communities'][place]
    assert r['support'][GROUPS[world][0]]==10
    assert not any(a['id']=='political:work:0' for a in offers(s,place))
    r['support']={g:40 for g in GROUPS[world]}
    # Refresh pointer: transaction helpers can replace the state dictionary.
    game.state=s
    local(client,'political:petition',place)
    r=game.state['offline_politics']['communities'][place]
    due=r['petitions'][0]['due'];before=copy.deepcopy(game.state.get('political_regions'))
    assert len(decision_tick(game.state,due-1,due))==1
    assert decision_tick(game.state,due,due+WEEK)==[]
    assert r['mandate']['office']=='Community representative'
    assert game.state.get('political_regions')==before


@pytest.mark.parametrize('world,place',[('Naruto','Konohagakure'),('One Piece','Cocoyasi Village'),('Bleach','Seireitei')])
def test_capture_is_one_holding_and_government_is_separate(world,place):
    from offline_politics import record_capture, tick_governments, writable, GROUPS, WEEK
    from military_resolution import resolve_operation
    s=state(world)
    s.update(location=place,canon_time_minutes=100000,canon_day=69,
             factions={'Player League':{},'Incumbent':{}},
             location_details={place:{'controlling_faction':'Incumbent'}},
             polity_state={'Player League':{'player_led':True}})
    op={'id':'first','target_location':place,'opponent':'Incumbent','military_evidence':{
        'basis':'Test fixture: confirmed supplied forces and surveyed defenses',
        'attacker_strength':200,'defender_strength':100,'fortification_multiplier':1,
        'access_confirmed':True,'supplies_confirmed':True}}
    resolve_operation(s,'Player League',{},op)
    assert s['location_details'][place]['controlling_faction']=='Incumbent'
    claim=s['political_regions'][-1]
    assert claim['hex_count']==1 and claim['scale']=='holding'
    resolve_operation(s,'Player League',{},op)
    assert len([r for r in s['political_regions'] if r.get('id')==claim['id']])==1
    occupation=s['offline_politics']['occupations'][place]
    assert occupation['status']=='occupied'
    community=writable(s,place);community['support']={g:50 for g in GROUPS[world]}
    occupation.update(status='charter_pending',charter_due=100001,government='council')
    assert len(tick_governments(s,100001))==1
    assert tick_governments(s,100001+WEEK)==[]
    assert claim['hex_count']==1 and occupation['status']=='governed'


def test_missing_epoch_does_not_suppress_future_negative_day_event():
    s,p=setup();s.pop('calendar_anchor_day',None)
    assert p['event_id'] in tick(s,s['canon_time_minutes'],p['opens'])[0]
