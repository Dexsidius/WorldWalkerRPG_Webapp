import copy
import json
import pytest
import runtime_mode
from test_reliability_update import session, state
from test_living_adventures import local
from offline_governance import tick, actions, WEEK


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(runtime_mode, 'MODE', 'offline')


def polity(world='Naruto', place='Konohagakure'):
    s=state(world)
    s.update(location=place, canon_time_minutes=100000, canon_day=69,
        factions={'Player League':{},'Incumbent':{}}, currency={'name':'Test','amount':100000},
        location_details={place:{'controlling_faction':'Incumbent','defender_strength':100,'fortification_multiplier':1}},
        polity_state={'Player League':{'player_led':True}},
        faction_clocks={'Player League':{'available_strength':200,'available_location':place,'operations':[]}})
    return s


@pytest.mark.parametrize('world,place',[('Naruto','Konohagakure'),('One Piece','Cocoyasi Village'),('Bleach','Seireitei')])
def test_real_survey_commit_and_capture(session,world,place):
    _,game,client=session
    game.state=polity(world,place)
    before=copy.deepcopy(game.state)
    assert actions(game.state,place)[0]['id']=='political:survey'
    assert game.state==before
    local(client,'political:survey',place)
    offer=next(a for a in actions(game.state,place) if a['id'].startswith('political:operation:'))
    local(client,offer['id'],place)
    s=game.state
    assert s['location_details'][place]['controlling_faction']=='Incumbent'
    assert s['offline_politics']['occupations'][place]['controller']=='Player League'
    assert s['faction_clocks']['Player League']['available_strength']==0
    assert not any(a['id'].startswith('political:operation:') for a in actions(s,place))


def test_no_invented_forces_or_defenses():
    s=polity();place=s['location']
    s['location_details'][place].pop('defender_strength')
    assert actions(s,place)==[]


def test_muster_excludes_unknown_absent_and_dead_members(session):
    _,game,client=session
    game.state=s=polity();place=s['location']
    s['faction_clocks']['Player League']['available_strength']=0
    s['faction_rosters']={'Player League':['Local','Unknown','Absent','Dead','Dismissed']}
    s['npc_memories']={'Local':{'last_known_location':place,'power_score':120},
        'Unknown':{'last_known_location':place}, 'Absent':{'last_known_location':'Elsewhere','power_score':500},
        'Dead':{'last_known_location':place,'power_score':900,'status':'Deceased','alive':False},
        'Dismissed':{'last_known_location':place,'power_score':300,'status':'Dismissed'}}
    offer=next(a for a in actions(s,place) if a['id'].startswith('political:muster:'))
    local(client,offer['id'],place)
    assert game.state['faction_clocks']['Player League']['available_strength']==120


def test_forces_cannot_teleport():
    s=polity();place=s['location']
    s['offline_governance']={'plans':{place:{'defender':'Incumbent','surveyed':100000,'strength':100,'fortification':1}}}
    s['faction_clocks']['Player League']['available_location']='Elsewhere'
    assert not any(a['id'].startswith('political:operation:') for a in actions(s,place))


def test_weekly_decisions_partition_save_load_and_retry():
    s=polity();a=copy.deepcopy(s);b=copy.deepcopy(s)
    tick(a,100000,100000+WEEK*12)
    for i in range(12):
        tick(b,100000+i*WEEK,100000+(i+1)*WEEK)
        b=json.loads(json.dumps(b))
    assert a['offline_governance']==b['offline_governance']
    saved=copy.deepcopy(a)
    assert tick(a,100000,100000+WEEK*12)==[]
    assert a==saved


def test_main_does_not_enroll(monkeypatch):
    s=polity();before=copy.deepcopy(s)
    monkeypatch.setattr(runtime_mode,'MODE','main')
    assert tick(s,100000,200000)==[] and actions(s,s['location'])==[]
    assert s==before


def test_repeated_capture_does_not_destroy_government():
    from offline_politics import record_capture
    s=polity();place=s['location']
    record_capture(s,'Player League',place,'Incumbent')
    s['offline_politics']['occupations'][place]['status']='governed'
    record_capture(s,'Player League',place,'Incumbent')
    assert s['offline_politics']['occupations'][place]['status']=='governed'


def test_malformed_optional_political_roots_recover():
    from offline_politics import writable
    s=polity();s['offline_politics']='old malformed data'
    assert writable(s,s['location'])=={'support':{},'last_work':{},'petitions':[]}


def test_liberation_does_not_overwrite_new_owner():
    from offline_world import liberate_arlong
    s=polity('One Piece','Cocoyasi Village')
    s['location_details']['Arlong Park']={'controlling_faction':'Arlong Pirates'}
    liberate_arlong(s)
    assert s['location_details']['Cocoyasi Village']['controlling_faction']=='Incumbent'
    assert s['location_details']['Arlong Park']['controlling_faction']=='Conomi Communities'
