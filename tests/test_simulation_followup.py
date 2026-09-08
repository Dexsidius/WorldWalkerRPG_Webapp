import copy
import json
import threading
import pytest
from test_reliability_update import session

def military():
    return {'world':'Naruto','campaign_id':'military-test','turn':10,'canon_time_minutes':1440,
            'location_details':{'Fort':{'controlling_faction':'Defenders','fortification_multiplier':3,'defender_strength':100}},
            'faction_clocks':{'Attackers':{'status':'turning_point','opponent':'Defenders','contested_location':'Fort','progress':100},
                              'Defenders':{'status':'active','power':5}}}

def evidence(attack=400):
    return {'basis':'Scouts confirmed the deployed forces and supply convoy','attacker_strength':attack,'defender_strength':100,
            'fortification_multiplier':3,'access_confirmed':True,'supplies_confirmed':True}

def test_both_military_entry_points_need_evidence():
    from systems import resolve_clock_conflicts
    from world_conflict import refresh
    a=military();b=military()
    b['faction_clocks']['Attackers']['operations']=[{'id':'op','type':'military','status':'active','progress':100,'target_location':'Fort'}]
    assert resolve_clock_conflicts(a)==[];refresh(b,0)
    assert a['location_details']==b['location_details']
    assert a['faction_clocks']['Attackers']['status']=='awaiting_resolution'
    assert b['faction_clocks']['Attackers']['operations'][0]['status']=='awaiting_resolution'

@pytest.mark.parametrize('attack,winner',[(250,'Defenders'),(400,'Attackers')])
def test_defenses_determine_battle_and_mutual_clock_does_not_replay(attack,winner):
    from systems import resolve_clock_conflicts
    s=military();s['faction_clocks']['Attackers']['military_evidence']=evidence(attack)
    s['faction_clocks']['Defenders'].update(opponent='Attackers',status='turning_point',contested_location='Fort')
    events=resolve_clock_conflicts(s)
    assert len(events)==1
    assert s['location_details']['Fort']['controlling_faction']==winner
    assert resolve_clock_conflicts(s)==[]
    assert s['faction_clocks']['Defenders']['status']!='destroyed'

def test_hidden_battle_resolves_without_public_message():
    from systems import resolve_clock_conflicts
    from world_conflict import public_view
    s=military();s['faction_clocks']['Attackers'].update(known_to_player=False,military_evidence=evidence())
    assert resolve_clock_conflicts(s)==[]
    assert not s.get('background_world_feed')
    assert public_view(s)['history']==[]
    assert s['location_details']['Fort']['controlling_faction']=='Attackers'

def test_unknown_opponent_and_missing_supply_never_get_default_power():
    from systems import resolve_clock_conflicts
    for mode in ('unknown','supply'):
        s=military();s['faction_clocks']['Attackers']['military_evidence']=evidence(10000)
        if mode=='unknown':s['faction_clocks'].pop('Defenders')
        else:s['faction_clocks']['Attackers']['military_evidence']['supplies_confirmed']=False
        resolve_clock_conflicts(s)
        assert s['location_details']['Fort']['controlling_faction']=='Defenders'

def property_state():
    return {'world':'Naruto','name':'Ren','canon_time_minutes':0,'location':'Konohagakure','currency':{'minor_per_major':100},
            'property_economy':{'last_tick_minute':0,'properties':[{'id':'p','type':'shop','name':'Shop','location':'Konohagakure','treasury':0,'facilities':{}}]}}

def test_property_income_batching_retries_and_saved_fraction():
    from property_economy import advance
    a=property_state();b=copy.deepcopy(a)
    for i in range(60):
        a['canon_time_minutes']+=1;advance(a,1)
        if i==30:a=json.loads(json.dumps(a))
    b['canon_time_minutes']=60;advance(b,60)
    assert a['property_economy']['properties']==b['property_economy']['properties']
    before=copy.deepcopy(b);advance(b,60)
    assert b==before

def test_new_property_does_not_earn_before_acquisition():
    from property_economy import advance
    s=property_state();s['canon_time_minutes']=60;s['property_economy']['properties'][0]['acquired_minute']=60
    advance(s,60)
    assert s['property_economy']['properties'][0]['treasury']==0

def test_finished_plans_make_room_and_keep_dependencies():
    from world_plans import advance
    s={'name':'Ren','turn':4,'world_plans':{str(i):{'id':str(i),'status':'completed','stages':[{'summary':'done','minutes':60}],'stage':1} for i in range(200)}}
    update={'op':'create','id':'new','actor':'Ren','evidence':'Ordered work','stages':[{'summary':'Follow-up complete','minutes':60,'routine':True,'requires':['0']}]}
    advance(s,0,[update]);assert 'new' in s['world_plans']
    assert len(s['world_plan_archive'])==160
    s['turn']=5;advance(s,60)
    assert s['world_plans']['new']['status']=='completed'

def test_real_active_plan_limit_records_diagnostic():
    from world_plans import advance
    s={'name':'Ren','turn':4,'world_plans':{str(i):{'status':'active','stages':[{'summary':'Work','minutes':600}]} for i in range(80)}}
    advance(s,0,[{'op':'create','id':'extra','actor':'Ren','evidence':'Order','stages':[{'summary':'work','minutes':60}]}])
    assert s['subsystem_health']['events'][-1]['code']=='active_plan_limit'

def test_mastery_needs_success_and_is_idempotent():
    from character_paths import record_turn,public_view
    s={'world':'Naruto','turn':2,'skills':{'Wind Step':{'description':'Movement'}}}
    record_turn({},s,['Could not use Wind Step'],5)
    assert public_view(s)['paths'][0]['mastery']==0
    outcomes=[{'skill':'Wind Step','success':True,'evidence':'Cleared the obstacle'}]
    record_turn({},s,outcomes,5);record_turn({},s,outcomes,5)
    assert public_view(s)['paths'][0]['mastery']==1

def test_training_segments_award_once_not_prose_plus_session():
    from character_paths import public_view,resolve_session,record_turn
    s={'world':'Naruto','turn':1,'canon_time_minutes':60,'resource':100,'resource_max':100,'skills':{'Wind Step':{'description':'Movement'}}}
    pid=public_view(s)['paths'][0]['id'];action='path:fundamentals:'+pid
    record_turn({},s,['Practice Wind Step'],60)
    resolve_session(s,action,60,False);resolve_session(s,action,60,False)
    assert public_view(s)['paths'][0]['mastery']==2.5
    s.update(turn=2,canon_time_minutes=120);resolve_session(s,action,60)
    assert public_view(s)['paths'][0]['mastery']==5

def test_infirmary_rest_preview_and_committed_recovery(session):
    _,game,client=session
    game.state.update(hp=10,resource=10,resource_max=100)
    game.state['property_economy']={'properties':[{'id':'p','type':'home','name':'Home','location':'Winston','facilities':{'infirmary':3}}]}
    q=client.post('/api/adventures/preview',json={'action':'rest:60','place':'Winston'}).get_json()
    from test_living_adventures import payload
    assert '16.32%' in json.dumps(q)
    r=client.post('/api/adventures/resolve',json=payload(q))
    assert r.status_code==200,r.get_json()
    assert game.state['hp']==26

def test_subsystem_failure_rolls_back_and_reports_without_leaking():
    from subsystem_safety import run,public_view
    s={'turn':1,'canon_time_minutes':60,'hp':10}
    def bad(local):local['hp']=99;raise ValueError('secret-key-and-private-npc-goal')
    assert not run(s,'test',bad)
    assert s['hp']==10
    assert 'secret-key' not in json.dumps(s)
    def good(local):local['hp']+=1
    assert run(s,'test',good);assert run(s,'test',good)
    assert s['hp']==11
    assert 'completed_token' not in json.dumps(public_view(s))

def org_payload(game):
    from test_v364_membership_truth import V364MembershipTruthTests
    from organizations import group_id
    game.state.update(V364MembershipTruthTests().yahiko_state())
    return {'request_id':'order-once','group_id':group_id('Akatsuki'),'task':'supply','members':['Nagato'],'target':'Amegakure'}

def test_org_command_receipt_retry_and_stale_guard(session):
    _,game,client=session;p=org_payload(game)
    from turn_recovery import guard
    previous_guard=guard(game.state)
    first=client.post('/api/organization-command',json=p);assert first.status_code==200,first.get_json()
    assert guard(game.state)!=previous_guard
    second=client.post('/api/organization-command',json=p);assert second.get_json()['replayed_request']
    assert len(game.state['organization_command']['assignments'])==1
    stale=client.post('/api/organization-command',json={**p,'request_id':'different','expected_guard':'stale'})
    assert stale.status_code!=200

def test_org_command_rolls_back_failed_autosave(session,monkeypatch):
    _,game,client=session;p=org_payload(game)
    monkeypatch.setattr(game,'autosave',lambda:(_ for _ in ()).throw(OSError('test save failure')))
    result=client.post('/api/organization-command',json=p)
    assert result.status_code!=200
    assert not game.state.get('organization_command',{}).get('assignments')

def test_org_command_cannot_race_locked_turn(session):
    _,game,client=session;p=org_payload(game)
    ready=threading.Event();release=threading.Event()
    def hold():
        with game.lock:ready.set();release.wait(5)
    worker=threading.Thread(target=hold);worker.start();ready.wait(5)
    try:assert client.post('/api/organization-command',json=p).status_code!=200
    finally:release.set();worker.join()
    assert not game.state.get('organization_command',{}).get('assignments')
