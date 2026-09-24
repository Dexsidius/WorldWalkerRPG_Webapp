"""Regression coverage for authored post-rescue consequences."""
import copy
import json

import pytest

import runtime_mode
import canon_consequences as consequences
import offline_canon_plans as plans
from offline_schedule import advance
from simulation_integrity import canon_dependency_graph
from test_offline_canon_plans import setup, arrive
from test_living_adventures import local as transact
from test_reliability_update import session


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(runtime_mode, 'MODE', 'offline')


CASES = (
    ('Naruto', "Yahiko's death and Akatsuki's transformation", 'Yahiko'),
    ('One Piece', "Ace's death", 'Portgas D. Ace'),
    ('Bleach', 'Renji and Byakuya come for Rukia', 'Rukia Kuchiki'),
)


def rescued(session, world, title):
    _, game, client = session
    game.state, plan = setup(world, title)
    if plan['private']:
        game.state['npc_memories'][plan['actors'][0]] = {
            'location': plan['place'], 'encounter_access': True,
        }
    arrive(game.state, plan)
    transact(client, 'worldevent:plan:' + plan['key'] + ':rescue', plan['place'])
    game.state['combat']['active'] = False
    plans.combat_finished(game, 'objective_complete')
    return game, client, plan


@pytest.mark.parametrize('world,title,target', CASES)
def test_rescue_opens_one_local_alternate_aftermath(session, world, title, target):
    game, client, plan = rescued(session, world, title)
    state = game.state
    row = consequences.read(state)[plan['event_id']]
    assert row['target'] == target and row['status'] == 'waiting'
    assert not consequences.actions(state, plan['place'])
    before = row['opens'] - 1
    state.update(canon_time_minutes=before, canon_day=before // 1440)
    advance(state, before, row['opens'])
    state.update(canon_time_minutes=row['opens'], canon_day=row['opens'] // 1440)
    assert row['status'] == 'available'
    choices = consequences.actions(state, plan['place'])
    assert any(a['id'].endswith(':help') for a in choices)
    assert any(a['id'].endswith(':leave') for a in choices)
    view = consequences.view(state, plan['place'])
    assert len(view) == 1 and target in view[0]['title']
    before = copy.deepcopy(state)
    consequences.actions(state, plan['place'])
    consequences.view(state, plan['place'])
    assert state == before
    action = next(a['id'] for a in choices if a['id'].endswith(':help'))
    start = state['canon_time_minutes']
    transact(client, action, plan['place'])
    assert game.state['canon_time_minutes'] == start + 60
    assert row['assisted'] and row['observed']
    assert not any(a['id'] == action for a in consequences.actions(state, plan['place']))
    assert len([e for e in state['consequence_ledger'] if e.get('source_event_id') == plan['event_id']]) == 2
    assert not any(x in json.dumps(state.get('affiliations', [])) for x in ('new rank', 'automatic victory'))
    assert 'offline_world' not in game.public_state()


@pytest.mark.parametrize('world,title,target', CASES)
def test_rescue_followup_advances_without_replaying_original_death(session, world, title, target):
    game, _, plan = rescued(session, world, title)
    state = game.state
    row = consequences.read(state)[plan['event_id']]
    start, end = state['canon_time_minutes'], row['due'] + 1
    advance(state, start, end)
    state.update(canon_time_minutes=end, canon_day=end // 1440)
    assert row['status'] == 'complete'
    assert row['resolution'] == consequences.FOLLOWUPS[title]['next']
    assert plans.rows(state)[plan['key']]['status'] == 'intervened'
    assert state['canon_events_fired'].count(plan['event_id']) == 1
    assert not consequences.actions(state, plan['place'])
    assert not consequences.view(state, plan['place'])
    assert all(target not in str(news.get('text', '')) for news in advance(state, end, end + 1)[1])


def test_alternate_aftermath_stays_private_when_player_travels_away(session):
    game, _, plan = rescued(session, 'One Piece', "Ace's death")
    state = game.state
    row = consequences.read(state)[plan['event_id']]
    state['location'] = 'Foosha Village'
    before, after = state['canon_time_minutes'], row['due'] + 1
    _, news = advance(state, before, after)
    assert row['status'] == 'complete'
    assert not any('rendezvous' in str(entry).lower() for entry in news)
    assert consequences.actions(state, plan['place']) == []
    assert consequences.view(state, plan['place']) == []


def test_rescue_record_is_idempotent_and_old_saves_do_not_gain_invented_outcomes(session):
    game, _, plan = rescued(session, 'Naruto', "Yahiko's death and Akatsuki's transformation")
    state = game.state
    original = copy.deepcopy(state)
    consequences.record_rescue(state, plan, 'Yahiko')
    assert state == original
    old, old_plan = setup('Naruto', "Yahiko's death and Akatsuki's transformation")
    old.update(canon_time_minutes=old_plan['due'] + 10000,
               canon_day=(old_plan['due'] + 10000) // 1440)
    advance(old, old['canon_time_minutes'], old['canon_time_minutes'] + 1)
    assert not consequences.read(old)


def test_alt_aftermath_is_split_skip_and_save_reload_stable(session):
    game, _, plan = rescued(session, 'Bleach', 'Renji and Byakuya come for Rukia')
    whole = copy.deepcopy(game.state)
    split = copy.deepcopy(game.state)
    row = consequences.read(whole)[plan['event_id']]
    start, end = whole['canon_time_minutes'], row['due'] + 1
    advance(whole, start, end)
    midpoint = row['opens']
    advance(split, start, midpoint)
    split = json.loads(json.dumps(split))
    advance(split, midpoint, end)
    assert consequences.read(whole) == consequences.read(split)
    assert whole['canon_event_states'] == split['canon_event_states']


def test_leaving_followup_preserves_npc_autonomy_until_deadline(session):
    game, client, plan = rescued(session, 'One Piece', "Ace's death")
    state = game.state
    row = consequences.read(state)[plan['event_id']]
    start = state['canon_time_minutes']
    advance(state, start, row['opens'])
    state.update(canon_time_minutes=row['opens'], canon_day=row['opens'] // 1440)
    action = next(a['id'] for a in consequences.actions(state, plan['place']) if a['id'].endswith(':leave'))
    transact(client, action, plan['place'])
    assert row['declined'] and row['status'] == 'available'
    assert not consequences.actions(state, plan['place'])
    advance(state, row['opens'], row['due'])
    assert row['status'] == 'complete'
    assert state['npc_intentions']['Portgas D. Ace']['status'] == 'active'


def test_later_death_cancels_followup_without_resurrecting_target(session):
    game, _, plan = rescued(session, 'Bleach', 'Renji and Byakuya come for Rukia')
    state = game.state
    row = consequences.read(state)[plan['event_id']]
    state['npc_memories']['Rukia Kuchiki'] = {'alive': False, 'status': 'dead'}
    advance(state, state['canon_time_minutes'], row['opens'])
    assert row['status'] == 'cancelled'
    assert state['npc_memories']['Rukia Kuchiki']['alive'] is False


@pytest.mark.parametrize('world,title,target', CASES)
def test_second_stage_choice_sets_specific_npc_plan_without_free_reward(session, world, title, target):
    game, client, plan = rescued(session, world, title)
    state = game.state
    row = consequences.read(state)[plan['event_id']]
    before = state['canon_time_minutes']
    advance(state, before, row['decision_opens'])
    state.update(canon_time_minutes=row['decision_opens'], canon_day=row['decision_opens'] // 1440)
    assert row['stage'] == 'decision'
    options = [a for a in consequences.actions(state, plan['place']) if a['id'].rsplit(':', 1)[-1]
               in consequences.FOLLOWUPS[title]['strategies']]
    assert len(options) == 2
    original_currency = copy.deepcopy(state.get('currency'))
    original_territory = copy.deepcopy(state.get('political_regions'))
    start = state['canon_time_minutes']
    transact(client, options[0]['id'], plan['place'])
    assert state['canon_time_minutes'] == start + 60
    assert row['status'] == 'complete' and row['strategy']
    assert state['npc_intentions'][target]['next_action']
    assert state.get('currency') == original_currency
    assert state.get('political_regions') == original_territory
    assert not consequences.actions(state, plan['place'])


def test_main_mode_keeps_confirmed_rescue_fact_but_offers_no_offline_choices(session, monkeypatch):
    game, _, plan = rescued(session, 'One Piece', "Ace's death")
    state = game.state
    monkeypatch.setattr(runtime_mode, 'MODE', 'main')
    assert not consequences.actions(state, plan['place'])
    assert not consequences.view(state, plan['place'])
    assert any('survived' in item['fact'] for item in consequences.ai_facts(state, 'Ace'))


@pytest.mark.parametrize('world,title,changed,unrelated', (
    ('Naruto', "Yahiko's death and Akatsuki's transformation", "Pain's Assault on Konoha", 'Ninja Registration Day'),
    ('One Piece', "Ace's death", 'Luffy begins two years of training', 'Landing in Wano'),
    ('Bleach', 'Renji and Byakuya come for Rukia', 'Rukia is sentenced to execution', 'Uryu Ishida makes himself known'),
))
def test_causal_graph_replaces_only_authored_dependents(session, world, title, changed, unrelated):
    game, _, plan = rescued(session, world, title)
    graph = {row['title']: row for row in canon_dependency_graph(game.state)['events']}
    assert graph[title]['status'] == 'replaced'
    assert graph[changed]['status'] in {'replaced', 'impossible'}
    assert graph[changed]['replacement'] == consequences.VARIANTS[title][changed]
    assert graph[unrelated]['status'] in {'upcoming', 'history'}
    assert not graph[unrelated]['replacement']


def test_old_confirmed_rescue_enrolls_followup_at_original_time(session):
    game, _, plan = rescued(session, 'One Piece', "Ace's death")
    state = game.state
    saved = consequences.read(state)[plan['event_id']]['saved_minute']
    state['offline_world'].pop('consequence_chains')
    original_ledger = copy.deepcopy(state['consequence_ledger'])
    advance(state, saved, saved + 1)
    row = consequences.read(state)[plan['event_id']]
    assert row['saved_minute'] == saved
    assert row['opens'] == saved + 60
    assert state['consequence_ledger'] == original_ledger


def test_old_intervened_row_that_was_not_a_success_does_not_invent_rescue():
    state, plan = setup('One Piece', "Ace's death")
    state['canon_time_minutes'] = plan['due'] + 1
    state['canon_day'] = state['canon_time_minutes'] // 1440
    plans.writable(state)[plan['key']] = {
        'title': plan['title'], 'status': 'intervened', 'attempted': True,
        'summary': 'You chose not to follow this scheduled plan.',
        'resolved_minute': plan['due'],
    }
    advance(state, state['canon_time_minutes'], state['canon_time_minutes'] + 1)
    assert not consequences.read(state)


@pytest.mark.parametrize('world,title,later_title', (
    ('Naruto', "Yahiko's death and Akatsuki's transformation", "Pain's Assault on Konoha"),
    ('One Piece', "Ace's death", 'Luffy begins two years of training'),
    ('Bleach', 'Renji and Byakuya come for Rukia', 'Rukia is sentenced to execution'),
))
def test_original_dependent_scene_is_replaced_in_calendar_not_replayed(session, world, title, later_title):
    game, _, plan = rescued(session, world, title)
    state = game.state
    later = next(p for p in plans.definitions(state) if p['title'] == later_title)
    start = state['canon_time_minutes']
    _, news = advance(state, start, later['due'] + 1)
    recorded = state['canon_event_states'][later['event_id']]
    assert recorded['status'] == 'replaced'
    assert recorded['replacement'] == consequences.VARIANTS[title][later_title]
    assert plans.rows(state)[later['key']]['status'] == 'cancelled'
    assert not any(entry.get('event_title') == later_title for entry in news)


def test_rukia_rescue_does_not_trigger_original_execution_raid_or_sokyoku_reveal(session):
    game, _, source = rescued(session, 'Bleach', 'Renji and Byakuya come for Rukia')
    state = game.state
    plans_by_title = {p['title']: p for p in plans.definitions(state)}
    for title in ('Rukia is sentenced to execution', 'Training with Urahara Kisuke',
                  'The push into Seireitei'):
        assert plans.guard(state, plans_by_title[title])
    from offline_world import definitions as legacy_definitions
    sokyoku = next(p for p in legacy_definitions(state) if p['key'] == 'sokyoku')
    assert sokyoku['invalid']
