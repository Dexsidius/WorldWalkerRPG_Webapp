"""Offline fork contracts: no network, real map, finite choices and durable outcomes."""
import copy
import pytest
from test_reliability_update import session, state
from test_living_adventures import quote, commit, local, payload
from living_adventures import action_list, recovery_rate, location_node
from offline_routes import creation, choices, NAMES, BACKGROUNDS
from offline_life import view, migrate
from worlds import WORLD_DATA
from systems import currency_balance
from simulation_integrity import _map_nodes, build_travel_graph

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('Offline game attempted a network request')
    import runtime_mode
    monkeypatch.setattr(runtime_mode,"MODE","offline")
    monkeypatch.setattr('urllib.request.urlopen',forbidden)

def choose(client,game,prefix):
    row=next(a for a in action_list(game.state,game.state['location']) if a['id'].startswith(prefix))
    return local(client,row['id'],game.state['location'])

@pytest.mark.parametrize('world',list(WORLD_DATA))
def test_choice_creation_current_worlds(session,world):
    app,game,client=session;c=choices(world)
    args=dict(world=world,name=NAMES[0],background=BACKGROUNDS[0][0],age=21,difficulty='Adventurer',
        origin=c['origins'][0],archetype=c['archetypes'][0],start_location=c['starts'][0]['location'],starting_era_id=c['eras'][0]['id'])
    r=client.post('/api/offline/create',json=args)
    assert r.status_code==200,r.get_json()
    assert game.state['opening_complete']
    assert location_node(game.state,game.state['location'])
    assert len(build_travel_graph(game.state)['nodes'])>3
    assert game.ai.provider=='offline'
    assert any(a['id'].startswith('offline:work:') for a in action_list(game.state,game.state['location']))

@pytest.mark.parametrize('world',list(WORLD_DATA))
def test_work_story_and_real_benefit(session,world):
    app,game,client=session;game.state=state(world);game.state['location']=_map_nodes(world)[0]['name']
    game.state['currency']={'name':'Test','amount':100000,'tracked':world!='Bleach'}
    before=copy.deepcopy(game.state)
    q=quote(client,'offline:work:0',game.state['location'])
    assert game.state==before
    data=payload(q);r=client.post('/api/adventures/resolve',json=data);assert r.status_code==200,r.get_json()
    assert game.state['offline_life']['career']==1
    cash=currency_balance(game.state)
    assert client.post('/api/adventures/resolve',json=data).status_code==200
    assert currency_balance(game.state)==cash and game.state['offline_life']['career']==1
    if world=='Bleach':assert cash==currency_balance(before)
    place=game.state['location'];rate=recovery_rate(game.state,place)
    for step in range(3):local(client,f'offline:story:{step}:0',place)
    assert view(game.state)['stories_completed']==1
    assert recovery_rate(game.state,place)==pytest.approx(rate*1.25)
    assert not any(a['id'].startswith('offline:story:') for a in action_list(game.state,place))

def test_contact_requires_meeting_trial_and_membership(session):
    app,game,client=session
    choose(client,game,'offline:meet:')
    assert not game.state['offline_life']['legacy']
    choose(client,game,'offline:trial:')
    choose(client,game,'offline:recruit:')
    assert 'joined' in game.state['offline_life']['recruits'].values()
    from organizations import roster_view
    roster=roster_view(game.state)
    assert game.state.get('official_party_group_id'),roster
    choose(client,game,'offline:bond:')
    assert not any(a['id'].startswith('offline:bond:') for a in action_list(game.state,game.state['location']) if a.get('person') in game.state['offline_life']['bonds'])

def test_free_text_routes_and_creation_reject_unlisted_values(session):
    app,game,client=session
    for path in ['/api/action/submit','/api/chats/send','/api/time/resolve','/api/advisor/ask','/api/campaign/new']:
        assert client.post(path,json={'text':'Invent anything'}).status_code==400
    c=choices('One Piece')
    with pytest.raises(ValueError):creation({'world':'One Piece','name':'Typed invented name'})

def test_story_supply_link_reduces_real_route(session):
    app,game,client=session;place=game.state['location']
    for step in range(2):local(client,f'offline:story:{step}:1',place)
    old=build_travel_graph(game.state)['edges'][place]
    edge=min(old,key=lambda e:e['minutes'])
    local(client,'offline:story:2:1',place)
    new=next(e for e in build_travel_graph(game.state)['edges'][place] if e['to']==edge['to'])
    assert new['minutes']<edge['minutes']

def test_migration_returns_legacy_location_to_current_map(session):
    app,game,client=session
    game.state['offline_choices']={'rpg':{'home':'Winston','node':1,'career':4}}
    game.state['location']='Winston \u2014 Field path'
    migrate(game.state)
    assert game.state['location']=='Winston'
    assert view(game.state)['career']==4

def test_chronicle_survives_delivery_reload_and_save(session):
    app,game,client=session
    local(client,'offline:work:0')
    first=client.get('/api/state').get_json()['tactical_story']
    assert any('Career experience' in row['text'] for row in first)
    assert client.get('/api/state').get_json()['tactical_story']==first
    game._flush_story()
    path=game.save()
    game.state={}
    from pathlib import Path
    loaded=client.post('/api/load',json={'name':Path(path).stem})
    assert loaded.status_code==200
    assert any('Career experience' in row['text'] for row in loaded.get_json()['story'])
    assert any('Career experience' in row['text'] for row in client.get('/api/state').get_json()['tactical_story'])

def test_unavailable_contact_does_not_complete_suspended_activity(session):
    app,game,client=session
    choose(client,game,'offline:meet:')
    row=next(a for a in action_list(game.state,game.state['location']) if a['id'].startswith('offline:trial:'))
    from living_adventures import action_spec
    spec=action_spec(game.state,{'place':game.state['location'],'action':row['id']})
    game.state.setdefault('adventures',{})['pending_activity']={'label':spec['label'],'spec':spec,'remaining_minutes':120}
    game.state['contacts'][spec['person']]['alive']=False
    minute=game.state['canon_time_minutes']
    r=client.post('/api/adventures/preview',json={'place':game.state['location'],'action':'activity:resume'})
    assert r.status_code==400
    assert game.state['canon_time_minutes']==minute
