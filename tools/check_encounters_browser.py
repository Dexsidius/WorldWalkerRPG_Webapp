"""Real game shell and signed encounter transactions, desktop and phone widths."""
import os
from pathlib import Path
import pytest
from check_reliability_browser import browser,ui
from test_campaign_encounters import seeded
from campaign_encounters import read


def reload_state(page):
    page.evaluate('apiGet("/api/state").then(r=>renderState(r.state)).then(()=>CampaignEncounters.refresh())')


def choose(page,id):
    page.locator(f'[data-encounter-choice="{id}"]').click()
    page.wait_for_selector('[data-confirm-yes]:not(:disabled)')
    page.locator('[data-confirm-yes]').click()
    page.wait_for_function('!APP.busy')
    page.wait_for_selector('#adventure-confirmation[open]',state='hidden')


@pytest.mark.parametrize('width',[1440,390])
def test_live_encounter_stages_confirm_cancel_and_mobile(ui,width):
    page,game,calls=ui
    page.set_viewport_size({'width':width,'height':900 if width>720 else 844})
    game.state=seeded('Naruto');reload_state(page)
    if width<720:
        page.locator('#mobile-bottom-nav [data-mobile-view="actions"]').click()
    page.locator('[data-encounter-begin]').click()
    page.wait_for_selector('[data-confirm-yes]:not(:disabled)')
    before=game.state['canon_time_minutes']
    page.locator('[data-confirm-cancel]').click()
    assert not read(game.state).get('active') and game.state['canon_time_minutes']==before
    page.locator('[data-encounter-begin]').click()
    page.wait_for_selector('[data-confirm-yes]:not(:disabled)')
    page.locator('[data-confirm-yes]').click()
    page.wait_for_function('!APP.busy')
    if width<720:page.locator('#mobile-bottom-nav [data-mobile-view="actions"]').click()
    page.locator('[data-encounter-open="original"]').click()
    assert page.locator('#encounter-heading').inner_text()=='The Forgotten Signal Post'
    assert not page.locator('[data-encounter-choice="encounter:prepared"]').count()
    choose(page,'encounter:investigate')
    page.wait_for_selector('[data-encounter-choice="encounter:prepared"]')
    assert 'washed-out footpaths' in page.locator('.encounter-page').inner_text()
    assert page.evaluate('document.querySelector("#campaign-encounter").scrollWidth <= document.querySelector("#campaign-encounter").clientWidth + 1')
    for box in page.locator('[data-encounter-choice]').all():assert box.bounding_box()['height']>=44
    out=os.getenv('WORLDWALKER_ENCOUNTER_SCREENSHOTS')
    if out:
        Path(out).mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(Path(out)/f'encounter-{width}.png'))
    choose(page,'encounter:prepared')
    page.wait_for_selector('[data-encounter-choice="encounter:close"]')
    assert 'What changed' in page.locator('.encounter-page').inner_text()
    assert read(game.state)['active']['changes'] and not calls
    choose(page,'encounter:close')
    page.wait_for_selector('#campaign-encounter[open]',state='hidden')
    assert not read(game.state).get('active')


def test_loading_other_campaign_closes_old_encounter(ui):
    page,game,_=ui
    game.state=seeded();reload_state(page)
    page.locator('[data-encounter-begin]').click()
    page.wait_for_selector('[data-confirm-yes]:not(:disabled)');page.locator('[data-confirm-yes]').click()
    page.wait_for_function('!APP.busy')
    page.locator('[data-encounter-open]').click()
    game.state=seeded();game.state['campaign_id']='another-campaign';reload_state(page)
    page.wait_for_selector('#campaign-encounter[open]',state='hidden')


def test_tactical_choice_leaves_encounter_window_and_requires_real_battle(ui):
    page,game,calls=ui
    game.state=seeded('Naruto','investigation');reload_state(page)
    page.locator('[data-encounter-begin]').click()
    page.wait_for_selector('[data-confirm-yes]:not(:disabled)');page.locator('[data-confirm-yes]').click()
    page.wait_for_function('!APP.busy')
    page.locator('[data-encounter-open]').click()
    page.locator('[data-encounter-choice="encounter:direct"]').click()
    page.wait_for_selector('[data-confirm-yes]:not(:disabled)');page.locator('[data-confirm-yes]').click()
    # Naruto intentionally navigates to its full-screen tactical app. The
    # Chronicle's APP global no longer exists in that separate document.
    page.wait_for_url('**/tactical-preview/**')
    assert not page.locator('#campaign-encounter[open]').count()
    assert game.state['combat']['active'] and game.state['combat']['tactical']['units']
    assert read(game.state)['active']['stage']=='combat'
    assert not read(game.state)['resolved'] and not calls


@pytest.mark.parametrize('width',[1440,390])
@pytest.mark.parametrize('world,title',[
    ('Naruto','Ninja Registration Day'),
    ('One Piece','Luffy leaves Foosha Village'),
    ('Bleach','Rukia Kuchiki arrives in Karakura Town'),
])
def test_authored_calendar_choices_render_and_commit(ui,monkeypatch,width,world,title):
    import runtime_mode
    from test_offline_canon_plans import setup,arrive
    from offline_canon_plans import rows
    monkeypatch.setattr(runtime_mode,'MODE','offline')
    page,game,calls=ui
    page.set_viewport_size({'width':width,'height':900 if width>720 else 844})
    game.state,p=setup(world,title);arrive(game.state,p);reload_state(page)
    if width<720:page.locator('#mobile-bottom-nav [data-mobile-view="actions"]').click()
    page.locator(f'[data-encounter-open="{p["key"]}"]').click()
    action='worldevent:plan:'+p['key']+':contribute'
    page.wait_for_selector(f'[data-encounter-choice="{action}"]')
    before=game.state['canon_time_minutes']
    page.locator(f'[data-encounter-choice="{action}"]').click()
    page.wait_for_selector('[data-confirm-yes]:not(:disabled)')
    page.locator('[data-confirm-cancel]').click()
    assert game.state['canon_time_minutes']==before
    assert not rows(game.state)[p['key']].get('contributed')
    assert page.evaluate('document.querySelector("#campaign-encounter").scrollWidth <= document.querySelector("#campaign-encounter").clientWidth + 1')
    for box in page.locator('[data-encounter-choice]').all():assert box.bounding_box()['height']>=44
    out=os.getenv('WORLDWALKER_ENCOUNTER_SCREENSHOTS')
    if out:
        Path(out).mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(Path(out)/f'canon-{world.lower().replace(" ","-")}-{width}.png'))
    choose(page,action)
    page.wait_for_function('!APP.busy')
    assert game.state['canon_time_minutes']==before+30
    assert rows(game.state)[p['key']]['contributed'] and not calls
