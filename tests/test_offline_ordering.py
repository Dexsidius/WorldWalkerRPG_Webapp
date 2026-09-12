import copy
import json
import pytest
import runtime_mode
from test_reliability_update import session
from test_offline_governance import polity
from offline_schedule import advance
from offline_politics import GROUPS, record_capture
from military_resolution import resolve_operation, defense_at


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(runtime_mode, 'MODE', 'offline')


def minute(day):
    return day*1440+480


def petition_state(due=12):
    s=polity('One Piece','Cocoyasi Village')
    s.update(canon_day=10,canon_time_minutes=minute(10),calendar_anchor_day=0,
             canon_events_fired=[],canon_divergences=[],npc_memories={})
    s['location_details']['Cocoyasi Village']['controlling_faction']='Arlong Pirates'
    s['factions']['Arlong Pirates']={}
    s['offline_politics']={'communities':{'Cocoyasi Village':{
        'support':{g:40 for g in GROUPS['One Piece']},
        'petitions':[{'status':'pending','due':minute(due)}]}},'occupations':{}}
    return s


@pytest.mark.parametrize('due,expected',[(12,'refused'),(14,'accepted'),(16,'accepted')])
def test_real_time_hook_long_skip_matches_split_save_load(session,due,expected):
    _,game,_=session
    initial=petition_state(due)
    def run(stops):
        game.state=copy.deepcopy(initial)
        before=minute(10)
        for day in stops:
            after=minute(day)
            game.state.update(canon_day=day,canon_time_minutes=after)
            game.fire_canon_events(before,after)
            game.state=json.loads(json.dumps(game.state))
            before=after
        return game.state
    a=run([30]);b=run(list(range(11,31)))
    assert a['offline_politics']==b['offline_politics']
    assert a['offline_governance']==b['offline_governance']
    assert a['offline_world']==b['offline_world']
    assert a['offline_politics']['communities']['Cocoyasi Village']['petitions'][0]['status']==expected
    assert a['location_details']['Cocoyasi Village']['controlling_faction']=='Conomi Communities'


def test_scheduler_preserves_caller_clock_and_retry():
    s=petition_state();s.update(canon_time_minutes=minute(30),canon_day=30)
    advance(s,minute(10),minute(30))
    assert (s['canon_time_minutes'],s['canon_day'])==(minute(30),30)
    before=copy.deepcopy(s)
    assert advance(s,minute(30),minute(30))==(set(),[])
    assert s==before


def test_scheduler_main_mode_noop(monkeypatch):
    s=petition_state();before=copy.deepcopy(s)
    monkeypatch.setattr(runtime_mode,'MODE','main')
    assert advance(s,minute(10),minute(30))==(set(),[])
    assert s==before


def test_charter_budgets_do_not_run_before_government_exists():
    s=polity();s.update(canon_day=10,canon_time_minutes=minute(10))
    record_capture(s,'Player League','Konohagakure','Incumbent')
    s['offline_politics']['communities']['Konohagakure']['support']={g:50 for g in GROUPS['Naruto']}
    s['offline_politics']['occupations']['Konohagakure'].update(
        status='charter_pending',government='council',charter_due=minute(12))
    a=copy.deepcopy(s);b=copy.deepcopy(s)
    advance(a,minute(10),minute(30))
    for day in range(11,31):
        advance(b,minute(day-1),minute(day))
    assert a['offline_governance']==b['offline_governance']
    assert a['offline_governance']['governments']['Konohagakure']['decisions']==2
    assert a['offline_politics']['occupations']['Konohagakure']['established']==minute(12)


def operation(ident, strength, defender='Incumbent', estimate=100):
    return {'id':ident,'target_location':'Konohagakure','opponent':defender,'military_evidence':{
        'basis':'Recorded local forces, surveyed defenses and supplies',
        'attacker_strength':strength,'defender_strength':estimate,'fortification_multiplier':1,
        'access_confirmed':True,'supplies_confirmed':True}}


def test_recapture_rejects_former_owner_and_uses_current_garrison():
    s=polity();s['factions']['Rival League']={}
    first=operation('first',200);resolve_operation(s,'Player League',{},first)
    assert defense_at(s,'Konohagakure')['defender_strength']==200
    stale=operation('stale',150);resolve_operation(s,'Rival League',{},stale)
    assert stale['status']=='awaiting_resolution'
    assert 'current control' in stale['blocked_reason']
    weak=operation('weak',150,'Player League',1);resolve_operation(s,'Rival League',{},weak)
    assert weak['status']=='failed'
    assert s['offline_politics']['occupations']['Konohagakure']['controller']=='Player League'
    strong=operation('strong',300,'Player League',1);resolve_operation(s,'Rival League',{},strong)
    assert strong['status']=='completed'
    holding=s['offline_politics']['occupations']['Konohagakure']
    assert holding['controller']=='Rival League' and holding['previous_controller']=='Player League'
    assert holding['garrison']['strength']==300
    assert s['location_details']['Konohagakure']['controlling_faction']=='Incumbent'
    before=copy.deepcopy(s)
    resolve_operation(s,'Rival League',{},strong)
    assert s==before


def test_unknown_old_holding_requires_evidence_not_former_garrison():
    s=polity();s['factions']['Rival League']={}
    record_capture(s,'Player League','Konohagakure','Incumbent')
    attempt=operation('legacy',5000,'Player League')
    resolve_operation(s,'Rival League',{},attempt)
    assert attempt['status']=='awaiting_resolution'
    assert 'current holding garrison' in attempt['blocked_reason']


def test_survey_reads_current_occupier_and_invalidates_old_plan():
    from offline_governance import actions, resolve
    s=polity();s['factions']['Rival League']={};s['faction_clocks']['Rival League']={}
    old=operation('capture',200);resolve_operation(s,'Rival League',{},old)
    s['offline_governance']={'plans':{'Konohagakure':{'defender':'Incumbent','surveyed':100000,'strength':100}}}
    assert not any(a['id'].startswith('political:operation:') for a in actions(s,'Konohagakure'))
    resolve(s,{'id':'political:survey','place':'Konohagakure'})
    plan=s['offline_governance']['plans']['Konohagakure']
    assert plan['defender']=='Rival League' and plan['strength']==200


def test_main_military_control_is_unchanged(monkeypatch):
    s=polity();monkeypatch.setattr(runtime_mode,'MODE','main')
    resolve_operation(s,'Player League',{},operation('main',200))
    assert s['location_details']['Konohagakure']['controlling_faction']=='Player League'
    assert 'offline_politics' not in s
