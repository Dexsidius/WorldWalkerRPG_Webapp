"""Real signed encounter choices, authored coverage and save/clock guarantees."""
import copy
import json
import pytest
from test_reliability_update import session, state
from test_living_adventures import local, quote, payload, commit
from campaign_encounters import catalog, record, view, offers, actions, read, ai_summary, participant_available
from encounter_content import STORIES
from living_adventures import location_node, SETTLEMENTS, combat_finished
from simulation_integrity import _map_nodes


@pytest.fixture(autouse=True)
def no_models(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('Encounters must not contact a model')
    monkeypatch.setattr('urllib.request.urlopen',forbidden)


def seeded(world='Overgeared',family='exploration'):
    s=state(world)
    s['location']=next(n['name'] for n in _map_nodes(world) if n.get('kind') in SETTLEMENTS and not (world=='Bleach' and any(x in n['name'].casefold() for x in ('hueco','las noches','hell','dangai','royal'))))
    s['adventures']={};s['companions']=[];s['canon_events_fired']=[]
    action={'training':'train:Control','exploration':'scout','work':'offline:work:0','social':'talk:someone','community':'offline:story:0:0','investigation':'mission:completed'}[family]
    record(s,action,s['location']);record(s,action,s['location'])
    return s


def begin(game,client,family='exploration',world='Overgeared'):
    game.state=seeded(world,family);place=game.state['location']
    local(client,'encounter:begin:'+family,place)
    return place


def test_authored_coverage():
    packs=[p for world in STORIES for p in catalog(world)]
    assert len(packs)==54 and len({p['id'] for p in packs})==54
    assert len({p['title'] for p in packs})==54
    assert all(len(catalog(w))==6 for w in STORIES)
    assert all(p['prepared_result']!=p['direct_result'] and p['finding']!=p['invitation'] for p in packs)
    assert catalog('Not a world')==[]


@pytest.mark.parametrize('world',list(STORIES))
@pytest.mark.parametrize('family',['training','exploration','work','social','community','investigation'])
def test_all_authored_branches_have_real_persistent_outcomes(session,world,family):
    _,game,client=session;place=begin(game,client,family,world)
    assert read(game.state)['active']['stage']=='opening'
    assert not any(a['id']=='encounter:prepared' for a in actions(game.state,place))
    local(client,'encounter:investigate',place)
    assert read(game.state)['active']['stage']=='decision'
    # JSON round-trip as on an old/reloaded save between stages.
    game.state=json.loads(json.dumps(game.state))
    before=copy.deepcopy(game.state.get('location_details',{}))
    local(client,'encounter:prepared',place)
    r=read(game.state);assert r['active']['stage']=='aftermath'
    assert r['active']['changes'] and r['active']['id'] in r['resolved']
    assert 'encounters' not in game.public_state().get('adventures',{})
    assert ai_summary(game.state)['established_changes']==r['active']['changes']
    if family=='community':assert game.state['location_details'][place]['adventure_shelter']
    else:assert r['active']['person'] in game.state['location_details'][place]['adventure_contacts']
    assert game.state['location_details'][place].get('controlling_faction')==before.get(place,{}).get('controlling_faction')
    id=r['active']['id'];local(client,'encounter:close',place)
    game.state['canon_time_minutes']+=3000
    assert id not in [p['id'] for p in offers(game.state,place)]


@pytest.mark.parametrize('family',['training','exploration','work','social','community'])
def test_direct_peaceful_branch_is_positive_and_does_not_force_fight(session,family):
    _,game,client=session;place=begin(game,client,family)
    local(client,'encounter:direct',place)
    assert read(game.state)['active']['method']=='direct'
    assert read(game.state)['active']['changes']
    assert not game.state.get('combat',{}).get('active')


def test_reads_cancel_and_retries_are_safe(session):
    _,game,client=session;game.state=seeded();place=game.state['location']
    before=copy.deepcopy(game.state)
    data=client.get('/api/adventures/location').get_json()
    assert data['encounters']['offers'] and game.state==before
    assert 'prepared_result' not in json.dumps(data['encounters'])
    q=quote(client,'encounter:begin:exploration',place)
    assert game.state==before
    assert client.post('/api/adventures/resolve',json={**payload(q),'confirmed':False}).status_code==400
    body=payload(q)
    assert client.post('/api/adventures/resolve',json=body).status_code==200
    end=copy.deepcopy(game.state)
    assert client.post('/api/adventures/resolve',json=body).get_json()['replayed_request']
    assert game.state==end
    assert 'prepared_result' not in json.dumps(ai_summary(game.state))


def test_only_completed_actions_create_evidence(session):
    _,game,client=session;game.state['adventures']={};place=game.state['location']
    assert offers(game.state,place)==[]
    quote(client,'scout',place);assert not read(game.state)
    local(client,'scout',place);assert offers(game.state,place)==[]
    local(client,'scout',place);assert any(p['family']=='exploration' for p in offers(game.state,place))


def test_stale_quote_and_missing_participant_cannot_finish(session):
    _,game,client=session;place=begin(game,client)
    q=quote(client,'encounter:investigate',place);r=read(game.state)['active']
    game.state['npc_memories'][r['person']]['alive']=False
    before=game.state['canon_time_minutes']
    assert client.post('/api/adventures/resolve',json=payload(q)).status_code==400
    assert game.state['canon_time_minutes']==before
    assert [a['id'] for a in actions(game.state,place)]==['encounter:leave']
    local(client,'encounter:leave',place)
    assert not read(game.state)['active']['changes']


def test_contacts_do_not_respawn_and_remote_places_have_no_offers():
    s=seeded();place=s['location'];p=offers(s,place)[0]
    name=p['author']+' of '+place
    s['npc_memories']={name:{'alive':False}}
    assert offers(s,place)==[]
    s['npc_memories'][name]={'alive':True,'location':'Elsewhere'}
    assert offers(s,place)==[]
    assert view(s,'Elsewhere')=={'offers':[]}


@pytest.mark.parametrize('world',list(STORIES))
@pytest.mark.parametrize('outcome',['objective_complete','fled'])
def test_investigation_uses_real_tactical_objective_and_settles_once(session,world,outcome):
    _,game,client=session;place=begin(game,client,'investigation',world)
    local(client,'encounter:direct',place)
    c=game.state['combat'];assert c['active'] and c['tactical']['units']
    assert c['adventure_objective']['rounds_required']==4
    assert read(game.state)['active']['stage']=='combat'
    assert read(game.state)['resolved']=={}
    combat_finished(game,outcome)
    r=read(game.state)
    assert bool(r['active']['changes'])==(outcome=='objective_complete')
    snapshot=copy.deepcopy(game.state)
    combat_finished(game,outcome);assert snapshot==game.state


@pytest.mark.parametrize('world',['Naruto','One Piece','Bleach'])
def test_canon_route_preparation_before_deadline_is_not_charged_twice(session,monkeypatch,world):
    import runtime_mode
    from test_offline_world import setup
    from offline_world import tick, appointment, encounter_view
    monkeypatch.setattr(runtime_mode,'MODE','offline')
    _,game,client=session;game.state,p=setup(world)
    tick(game.state,game.state['canon_time_minutes'],p['due']-50)
    game.state.update(canon_time_minutes=p['due']-50,canon_day=(p['due']-50)//1440)
    local(client,'worldevent:prepare:'+p['key'],p['place'])
    assert game.state['canon_time_minutes']==p['due']-20
    assert appointment(game.state,p)['withdrawal_prepared']
    assert p['event_id'] not in game.state['canon_events_fired']
    assert 'four rounds' not in encounter_view(game.state,p['place'])[0]['narrative']
    local(client,'worldevent:'+p['key'],p['place'])
    assert game.state['combat']['adventure_objective']['rounds_required']==3


def test_main_canon_scheduler_is_not_replaced(monkeypatch):
    import runtime_mode
    from offline_world import encounter_view
    monkeypatch.setattr(runtime_mode,'MODE','main')
    s=seeded('Naruto');assert encounter_view(s,s['location'])==[]


def test_existing_companion_opens_positive_social_story_without_new_counter():
    s=state();s['adventures']={}
    s['companions']=[{'name':'Friend','status':'active','alive':True,'location':s['location']}]
    assert any(p['family']=='social' for p in offers(s,s['location']))


def test_interruption_preserves_stage_and_resumes_remaining_time(session):
    _,game,client=session;place=begin(game,client)
    game.state.update(canon_time_minutes=10*1440+475,canon_day=10)
    game.state['scheduled_events']=[{'title':'Meet the courier','location':place,'due_canon_day':10}]
    result=local(client,'encounter:investigate',place)
    assert result['interrupted'] and read(game.state)['active']['stage']=='opening'
    assert game.state['adventures']['pending_activity']['remaining_minutes']==25
    local(client,'activity:resume',place)
    assert read(game.state)['active']['stage']=='decision'
    assert game.state['canon_time_minutes']==10*1440+505


def test_partial_training_does_not_unlock_encounter_until_completed(session):
    _,game,client=session;game.state['adventures']={};place=game.state['location']
    game.state.update(canon_time_minutes=10*1440+475,canon_day=10,resource=100,resource_max=100)
    game.state['scheduled_events']=[{'title':'Meet the courier','location':place,'due_canon_day':10}]
    stat=next(iter(game.state['stats']))
    local(client,'train:'+stat,place)
    assert not read(game.state).get('signals')
    local(client,'activity:resume',place)
    assert read(game.state)['signals'][place+'|training']['count']==1


def test_fixed_enemy_power_does_not_follow_player_stats(session):
    _,game,client=session;powers=[]
    for value in (20,2000):
        game.state=seeded('Naruto','investigation');place=game.state['location']
        game.state['stats']={k:value for k in game.state['stats']}
        local(client,'encounter:begin:investigation',place)
        local(client,'encounter:direct',place)
        powers.append(game.state['combat']['enemy']['power'])
    assert powers==[60,60]


def test_main_prompt_contains_only_observed_encounter_facts(session):
    _,game,client=session;place=begin(game,client)
    p=next(p for p in catalog(game.state['world']) if p['family']=='exploration')
    context=json.dumps(game.trimmed_state_for_ai('What is happening here?'))
    assert p['invitation'] in context
    assert p['finding'] not in context and p['prepared_result'] not in context
    assert 'signals' not in context
    local(client,'encounter:investigate',place)
    context=json.dumps(game.trimmed_state_for_ai('What have I verified?'))
    assert p['finding'] in context and p['prepared_result'] not in context


def test_canon_followup_closes_scene_without_extra_reward(session,monkeypatch):
    import runtime_mode
    from test_offline_world import setup
    from offline_world import tick, encounter_view
    monkeypatch.setattr(runtime_mode,'MODE','offline')
    _,game,client=session;game.state,p=setup()
    tick(game.state,game.state['canon_time_minutes'],p['opens'])
    game.state.update(canon_time_minutes=p['opens'],canon_day=p['opens']//1440)
    local(client,'worldevent:'+p['key'],p['place'])
    combat_finished(game,'objective_complete');game.state['combat']['active']=False
    before=copy.deepcopy(game.state['currency'])
    local(client,'worldevent:followup:'+p['key'],p['place'])
    assert game.state['currency']==before and encounter_view(game.state,p['place'])==[]
