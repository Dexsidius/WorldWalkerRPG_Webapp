"""Coverage, migrations, conditional choices and no-omniscience regressions."""
import copy
import json
import pytest
import runtime_mode
from canon_event_plans import catalog, REQUIRES
from worlds import timeline_for
import offline_canon_plans as plans
from offline_schedule import advance
from test_reliability_update import state, session
from test_living_adventures import local as transact

WORLDS = ('Naruto', 'One Piece', 'Bleach')


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(runtime_mode, 'MODE', 'offline')


def setup(world='Naruto', title='Ninja Registration Day'):
    s = state(world)
    s.update(canon_events_fired=[], canon_divergences=[], canon_event_states={},
             npc_memories={}, contacts={}, companions=[], calendar_anchor_day=-30000)
    p = next(p for p in plans.definitions(s) if p['title'] == title)
    s.update(location=p['place'], canon_time_minutes=p['depart']-1, canon_day=(p['depart']-1)//1440)
    return s, p


def arrive(s, p):
    before = s['canon_time_minutes']
    s.update(canon_time_minutes=p['opens'], canon_day=p['opens']//1440)
    advance(s, before, p['opens'])


@pytest.mark.parametrize('world,count', [('Naruto',52),('One Piece',40),('Bleach',27)])
def test_every_timeline_entry_has_explicit_authored_plan(world, count):
    events = timeline_for(world)['events']
    data = catalog(world)
    assert len(data) == count
    assert set(data) == {e['title'] for e in events}
    for p in data.values():
        assert p['actors'] and p['offer'] and p['contribution'] and p['brief']
        assert set(p['requires']) <= set(data)
    # IDs are joined by exact title, never calendar array position.
    ids = [p['key'] for p in plans.definitions(state(world))]
    assert len(ids) == len(set(ids))


CASES = [(w,e['title']) for w in WORLDS for e in timeline_for(w)['events']
         if not e.get('historical_only') and e['title'] not in plans.LEGACY]


@pytest.mark.parametrize('world,title', CASES)
def test_each_plan_schedules_and_resolves_only_once(world, title):
    s,p = setup(world, title)
    if p['private']:
        s['npc_memories'][p['actors'][0]] = {'location':p['place'], 'encounter_access':True}
    arrive(s,p)
    assert plans.rows(s)[p['key']]['status'] == 'available'
    choices = plans.actions(s,p['place'])
    assert any(a['id'].endswith(p['key']+':contribute') for a in choices)
    before = copy.deepcopy(s)
    plans.view(s,p['place']);plans.visible_parties(s);plans.actions(s,p['place'])
    assert s == before
    s.update(canon_time_minutes=p['due'], canon_day=p['due']//1440)
    advance(s,p['opens'],p['due'])
    assert plans.rows(s)[p['key']]['status'] == 'occurred'
    assert s['canon_events_fired'].count(p['event_id']) == 1
    assert not any(n['event_title'] == title for n in advance(s,p['due'],p['due']+1)[1])


@pytest.mark.parametrize('world,title', [('Naruto','Ninja Registration Day'),
    ('One Piece','Luffy leaves Foosha Village'),('Bleach','Rukia Kuchiki arrives in Karakura Town')])
def test_real_timed_choice_is_exact_and_cannot_farm(session, world, title):
    _,game,client = session
    game.state,p = setup(world,title);arrive(game.state,p)
    original = game.state['canon_time_minutes']
    action = 'worldevent:plan:'+p['key']+':contribute'
    transact(client,action,p['place'])
    assert game.state['canon_time_minutes'] == original+30
    r = plans.rows(game.state)[p['key']]
    assert r['contributed'] and r['observed']
    assert r['history'][-1]['text'] == p['contribution']
    assert not any(a['id'] == action for a in plans.actions(game.state,p['place']))
    assert r['status'] == 'available'  # Not an automatic canon victory.


def test_observe_does_not_reveal_private_outcome_or_future_schedule():
    s,p = setup('One Piece',"Nefertari Cobra's death and Imu's reveal")
    arrive(s,p)
    assert plans.actions(s,p['place']) == []
    assert plans.view(s,p['place']) == []
    assert plans.visible_parties(s) == []
    s['npc_memories']['Nefertari Cobra'] = {'location':p['place'],'encounter_access':True}
    views = [v for v in plans.view(s,p['place']) if v['key'] == p['key']]
    assert views and 'Imu' not in json.dumps(views)
    s.update(canon_time_minutes=p['due'],canon_day=p['due']//1440,location='Foosha Village')
    assert not any(n['event_title']==p['title'] for n in advance(s,p['opens'],p['due'])[1])


def test_dead_or_captured_actor_blocks_original_plan_without_resurrection():
    for m in ({'alive':False},{'status':'captured'}):
        s,p = setup();s['npc_memories']['Naruto Uzumaki'] = m.copy()
        arrive(s,p)
        assert plans.rows(s)[p['key']]['status'] == 'cancelled'
        assert s['npc_memories']['Naruto Uzumaki'] == m
        assert not any(v['key']==p['key'] for v in plans.view(s,p['place']))


def test_canon_player_is_never_automatically_run_by_schedule(session):
    _,game,client = session
    s,p = setup();game.state=s;s['name']='Naruto Uzumaki'
    arrive(s,p)
    s['canon_time_minutes']=p['due']+1440
    advance(s,p['opens'],s['canon_time_minutes'])
    assert plans.rows(s)[p['key']]['status']=='awaiting_player'
    assert p['event_id'] not in s['canon_events_fired']
    assert not any(n['name']=='Naruto Uzumaki' for n in plans.visible_parties(s))
    transact(client,'worldevent:plan:'+p['key']+':decline',p['place'])
    assert plans.rows(game.state)[p['key']]['status']=='intervened'
    assert game.state['location']==p['place']


def test_rescue_is_real_tactical_objective_and_not_whole_war_win(session):
    _,game,client = session
    game.state,p=setup('One Piece',"Ace's death")
    arrive(game.state,p)
    transact(client,'worldevent:plan:'+p['key']+':rescue',p['place'])
    goal=game.state['combat']['adventure_objective']
    assert goal['world_event']==p['key'] and goal['kind']=='protection'
    assert game.state['combat']['enemy']['power']==800
    plans.combat_finished(game,'objective_complete')
    assert plans.rows(game.state)[p['key']]['status']=='intervened'
    assert 'wider conflict is not automatically won' in plans.rows(game.state)[p['key']]['summary']
    saved=copy.deepcopy(game.state)
    plans.combat_finished(game,'objective_complete')
    assert game.state==saved


def test_explicit_dependencies_do_not_cancel_unrelated_wano():
    s,p=setup('One Piece',"Ace's death");arrive(s,p)
    plans.finish(s,p,plans.writable(s)[p['key']],'intervened','Ace was rescued.')
    training=next(p for p in plans.definitions(s) if p['title']=='Luffy begins two years of training')
    wano=next(p for p in plans.definitions(s) if p['title']=='The Raid on Onigashima — Wano liberated')
    assert plans.guard(s,training)
    assert not plans.guard(s,wano)


def test_old_saves_do_not_replay_elapsed_history(session):
    _,game,_=session;game.state,p=setup()
    game.state.update(canon_time_minutes=p['due']+1440,canon_day=p['due']//1440+1)
    news=game.fire_canon_events(game.state['canon_time_minutes'],game.state['canon_time_minutes']+1)
    assert not any(n.get('event_title')==p['title'] for n in news)
    assert p['key'] not in plans.rows(game.state)


@pytest.mark.parametrize('world', WORLDS)
def test_split_time_and_save_reload_produce_same_plans(world):
    s=state(world);s.update(canon_time_minutes=0,canon_day=0,calendar_anchor_day=0,
                           canon_divergences=[],canon_events_fired=[],npc_memories={},contacts={})
    whole=copy.deepcopy(s);split=copy.deepcopy(s)
    advance(whole,0,100*1440)
    for day in range(100):
        advance(split,day*1440,(day+1)*1440)
        split=json.loads(json.dumps(split))
    assert plans.rows(whole)==plans.rows(split)
    assert plans.positions(whole)==plans.positions(split)


def test_distant_marker_needs_tracking_and_legal_route():
    s,p=setup();s.update(location='Sunagakure',companions=[{'name':'Naruto Uzumaki','alive':True}],
                       npc_memories={'Naruto Uzumaki':{'location':'Sunagakure'}})
    advance(s,s['canon_time_minutes'],p['depart']+1);s['canon_time_minutes']=p['depart']+1
    assert not plans.visible_parties(s)
    s['npc_memories']['Naruto Uzumaki']['tracking_confirmed']=True
    assert any(n['name']=='Naruto Uzumaki' for n in plans.visible_parties(s))
    s['npc_memories']['Naruto Uzumaki']['location']='Unmapped realm'
    plans.writable(s)[p['key']]['origins']['Naruto Uzumaki']='Unmapped realm'
    assert not plans.visible_parties(s)


def test_main_mode_does_not_schedule_or_offer_any_new_choices(monkeypatch):
    s,p=setup();before=copy.deepcopy(s);monkeypatch.setattr(runtime_mode,'MODE','main')
    assert plans.definitions(s)==[] and plans.actions(s,p['place'])==[]
    assert plans.tick(s,p['depart'],p['due'])==(set(),[])
    assert s==before


def test_same_day_scenes_cannot_overlap_their_intervention_windows():
    s,_=setup('One Piece',"Ace's death")
    all_plans=plans.definitions(s)
    battle=next(p for p in all_plans if p['title']=='The Battle of Marineford')
    ace=next(p for p in all_plans if p['title']=="Ace's death")
    assert battle['due'] < ace['opens'] < ace['due']
    assert battle['due']//1440==ace['due']//1440==68


def test_captive_roles_can_be_sentenced_or_rescued_but_dead_roles_cannot():
    s,p=setup('Bleach','Rukia is sentenced to execution')
    s['npc_memories']['Rukia']={'status':'captured'}
    assert not plans.guard(s,p)
    s['npc_memories']['Rukia']['alive']=False
    assert plans.guard(s,p)


def test_obito_rescue_blocks_only_explicit_incompatible_continuations():
    s,p=setup('Naruto','The Kannabi Bridge mission');arrive(s,p)
    plans.finish(s,p,plans.writable(s)[p['key']],'intervened','Obito escapes with his team.')
    children={q['title']:q for q in plans.definitions(s)}
    assert plans.guard(s,children["Naruto's birth and the Nine-Tails attack"])
    assert not plans.guard(s,children['Ninja Registration Day'])


def test_private_schedule_and_actual_positions_do_not_leak_from_public_state(session):
    _,game,_=session;game.state,p=setup();arrive(game.state,p)
    assert plans.positions(game.state)
    public=game.public_state()
    assert 'offline_world' not in public
    assert 'actor_positions' not in public


def test_explicit_delay_changes_schedule_without_changing_event_identity():
    s,p=setup()
    s['canon_divergences']=[{'event_id':p['event_id'],'status':'delayed','new_day':50}]
    delayed=next(q for q in plans.definitions(s) if q['key']==p['key'])
    assert delayed['event_id']==p['event_id'] and delayed['due']//1440==50


def test_local_activity_stops_at_a_new_encounter_window(session):
    _,game,client=session;game.state,p=setup('Naruto','D-rank missions begin')
    game.state.update(canon_time_minutes=p['opens']-60,canon_day=(p['opens']-60)//1440,currency={'name':'Ryo','amount':100000})
    transact(client,'political:work:0',p['place'])
    assert game.state['canon_time_minutes']==p['opens']
    assert game.state['adventures']['pending_activity']['remaining_minutes']>0
