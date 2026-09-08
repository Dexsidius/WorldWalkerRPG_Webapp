"""Real offline shell coverage catches main UI changes that break the adapter."""
import copy
import pytest
from check_reliability_browser import browser, ui

@pytest.fixture(autouse=True)
def offline_mode(monkeypatch):
    import runtime_mode
    monkeypatch.setattr(runtime_mode,'MODE','offline')

def assert_no_typing(page):
    assert page.evaluate('''() => [...document.querySelectorAll('input,textarea,[contenteditable=true]')].filter(e =>
      !e.disabled && !e.readOnly && !['checkbox','radio','range','file','hidden','button','submit'].includes(e.type)
      && getComputedStyle(e).visibility==='visible' && e.getClientRects().length).length''')==0

@pytest.mark.parametrize('mobile',[False,True])
def test_event_marker_opens_intervention_without_journal_or_state_change(ui,mobile):
    from test_offline_world import setup
    from offline_world import tick
    page,game,_=ui
    game.state,pack=setup()
    tick(game.state,game.state['canon_time_minutes'],pack['opens'])
    game.state.update(canon_time_minutes=pack['opens'],canon_day=pack['opens']//1440,opening_complete=True)
    if mobile:page.set_viewport_size({'width':390,'height':844})
    page.reload()
    page.wait_for_function("APP.state?.world==='Naruto'")
    if page.locator('#modal-patch-notes.open').count():
        page.locator('#modal-patch-notes button').last.click()
    if mobile:
        page.locator('#mobile-bottom-nav [data-mobile-view="map"]').click()
    else:page.locator('#workspace-map-tab').click()
    page.get_by_role('button',name='Might Duy · Encounter participant',exact=True).click()
    page.get_by_role('button',name='View encounter choices',exact=True).click()
    page.locator('[data-town-action="worldevent:duy"]').click()
    page.wait_for_selector('#adventure-confirmation[open]')
    before=copy.deepcopy(game.state)
    page.locator('[data-confirm-cancel]').click()
    assert game.state==before
    assert not page.locator('#modal-journal.open').count()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')

def test_offline_work_cancel_confirm_and_chronicle_reload(ui):
    page,game,_=ui
    page.locator('#offline-play [data-category="Work"]').click()
    page.wait_for_selector('[data-activity="offline:work:0"]')
    before=copy.deepcopy(game.state)
    page.locator('[data-activity="offline:work:0"]').click()
    page.wait_for_selector('#adventure-confirmation[open]')
    page.locator('[data-confirm-cancel]').click()
    assert game.state==before
    page.locator('[data-activity="offline:work:0"]').click()
    page.locator('[data-confirm-yes]').click()
    page.wait_for_function('APP.state.offline_life?.career===1')
    assert game.state['canon_time_minutes']==before['canon_time_minutes']+480
    page.reload()
    page.wait_for_function("document.querySelector('#story-feed')?.innerText.includes('Career experience 1')")
    assert_no_typing(page)

def test_offline_creation_and_mobile_map_remain_playable(ui):
    page,game,_=ui
    page.get_by_role('button',name='GAME',exact=True).click()
    page.locator('[data-action="new-campaign"]').click()
    page.wait_for_selector('#offline-creator[open]')
    assert_no_typing(page)
    page.locator('#offline-creator select[name="world"]').select_option('One Piece')
    page.get_by_role('button',name='Begin this life',exact=True).click()
    page.wait_for_function("APP.state?.world==='One Piece' && APP.state.opening_complete")
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#mobile-bottom-nav [data-mobile-view="actions"]').click()
    page.wait_for_selector('#offline-play [data-map]')
    assert page.locator('#mobile-advance-dock').is_hidden()
    page.locator('#offline-play [data-map]').click()
    page.wait_for_selector('#living-map-main')
    page.wait_for_selector('[data-offline-map-choice]')
    assert page.locator('[data-offline-map-choice] option').count()>3
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert_no_typing(page)
