import copy
import json
import pytest
from world_conflict import refresh, public_view, sanitize_public, operations_at, resolve_intervention, resolution_context
from character_paths import pin, public_view as paths, actions, resolve_session
from organization_command import advance

def state():
    return {'world':'Naruto','name':'Ren','campaign_id':'regression','turn':1,'canon_day':0,'canon_time_minutes':480,
            'location':'Konohagakure','skills':{'Wind Step':{'description':'Movement technique'}},
            'faction_clocks':{'Raiders':{'operations':[{'id':'op','type':'military','objective':'Attack Konohagakure','target_location':'Konohagakure','progress':0,'status':'active'}]}}}

def op(s): return s['faction_clocks']['Raiders']['operations'][0]

def test_operation_time_is_batch_independent_save_safe_and_retry_safe():
    short=state();long=state()
    for i in range(144):
        short['canon_time_minutes']+=5; refresh(short,5)
        if i==60: short=json.loads(json.dumps(short))
    long['canon_time_minutes']+=720;refresh(long,720)
    assert op(short)['progress']==op(long)['progress']==2
    refresh(long,720)
    assert op(long)['progress']==2

def test_legacy_clock_does_not_advance_operation_twice():
    from systems import tick_world_clocks
    s=state();s['canon_time_minutes']+=360
    tick_world_clocks(s,360);refresh(s,360)
    assert op(s)['progress']==1

def test_military_preparation_never_captures_territory():
    s=state();s['location_details']={'Konohagakure':{'controlling_faction':'Konoha','fortification':5,'defender_power':10000}}
    before=copy.deepcopy(s['location_details']);op(s)['progress']=99
    s['canon_time_minutes']+=360;refresh(s,360)
    assert op(s)['status']=='awaiting_resolution'
    assert s['location_details']==before
    assert resolution_context(s)['pending'][0]['id']=='op'
    from systems import _normalize_faction_strategy
    _normalize_faction_strategy(s,'Raiders',s['faction_clocks']['Raiders'])
    assert len(s['faction_clocks']['Raiders']['operations'])==1

@pytest.mark.parametrize('field,value',[('visibility','hidden'),('known_to_player',False)])
def test_hidden_operation_not_in_player_views_or_actions(field,value):
    s=state();op(s).update({field:value,'objective':'Secret assassination'})
    s['world_conflict']={'history':[{'id':'op','faction':'Raiders','summary':'Secret assassination','known_to_player':False}]}
    s['background_world_feed']=[{'summary':'Secret assassination'}]
    original=copy.deepcopy(s)
    assert public_view(s)['operations']==[]
    assert operations_at(s,'Konohagakure')==[]
    with pytest.raises(ValueError):resolve_intervention(s,'conflict:assist:Raiders:op',120)
    local=copy.deepcopy(s);sanitize_public(local)
    assert 'Secret assassination' not in json.dumps(local)
    assert s==original

def test_completed_secret_operation_does_not_emit_public_news():
    s=state();op(s).update(type='economic',progress=99,known_to_player=False)
    s['canon_time_minutes']+=360;refresh(s,360)
    assert not s.get('background_world_feed')
    assert not public_view(s)['history']

def mentor_state():
    s=state();s['npc_memories']={'Teacher':{'role':'Sensei','location':'Konohagakure'}}
    pin(s,paths(s)['paths'][0]['id']);return s

def test_empty_people_list_does_not_mean_every_mentor():
    s=mentor_state()
    assert not [a for a in actions(s,[]) if ':mentor:' in a['id']]
    assert [a for a in actions(s,[{'name':'Teacher'}]) if ':mentor:' in a['id']]

@pytest.mark.parametrize('change',[{'status':'dead'},{'alive':False},{'location':'Amegakure'}])
def test_training_rechecks_mentor_at_resolution(change):
    s=mentor_state();a=next(a for a in actions(s) if ':mentor:' in a['id'])
    s['npc_memories']['Teacher'].update(change);before=copy.deepcopy(s)
    assert not [a for a in actions(s) if ':mentor:' in a['id']]
    with pytest.raises(ValueError):resolve_session(s,a['id'],180)
    assert s==before

def test_dead_member_assignment_cannot_return_or_pay_out():
    s=state();s['npc_memories']={'Kaito':{'status':'dead','alive':False}}
    s['organization_command']={'assignments':{'a':{'id':'a','group_id':'old-team','task':'supply','label':'Supply','members':['Kaito'],'status':'active','started_minute':0,'due_minute':100}},'reports':[],'projects':{}}
    advance(s,500)
    a=s['organization_command']['assignments']['a']
    assert a['status']=='cancelled'
    assert 'returned' not in a['report']
    advance(s,500)
    assert len(s['organization_command']['reports'])==1

def test_runtime_artifact_guard():
    from check_tracked_runtime import forbidden
    assert forbidden('.build-test-data/autosave.json')
    assert forbidden('data/friend_server_secret.txt')
    assert not forbidden('tests/test_friend_server.py')

def test_assignment_valid_team_still_finishes_and_dead_member_does_not():
    from test_v364_membership_truth import V364MembershipTruthTests
    from organization_command import start_assignment
    from organizations import group_id
    s=V364MembershipTruthTests().yahiko_state();s['canon_time_minutes']=480
    a=start_assignment(s,group_id('Akatsuki'),'supply',['Nagato'],'Amegakure')
    live=copy.deepcopy(s)
    live['canon_time_minutes']=a['due_minute'];advance(live,2160)
    assert live['organization_command']['assignments'][a['id']]['status'] in {'completed','failed'}
    s['npc_memories']['Nagato']['alive']=False
    s['canon_time_minutes']=a['due_minute'];advance(s,2160)
    assert s['organization_command']['assignments'][a['id']]['status']=='cancelled'

def test_public_state_and_panels_hide_operations_without_mutating_save(tmp_path,monkeypatch):
    from game import GameSession
    import app as web
    g=GameSession(save_dir=tmp_path/'saves',settings_path=tmp_path/'settings.json')
    g.state.update(state());op(g.state).update(known_to_player=False,objective='Unique secret mission')
    original=copy.deepcopy(g.state['faction_clocks'])
    assert 'Unique secret mission' not in json.dumps(g.public_state())
    monkeypatch.setattr(web,'game',g)
    with web.app.test_request_context('/api/panels'):
        response=web.api_panels()
    assert response.status_code==200
    assert 'Unique secret mission' not in response.get_data(as_text=True)
    assert g.state['faction_clocks']==original
