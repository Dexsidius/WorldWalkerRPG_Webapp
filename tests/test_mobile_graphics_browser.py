"""Device quality never changes campaign state or combat geometry."""
import copy
import pytest
from check_reliability_browser import browser, ui


def test_phone_auto_is_vector_and_quality_persists(ui):
    page,game,calls=ui
    game.state.update(world='Naruto',location='Konohagakure')
    page.set_viewport_size({'width':390,'height':844})
    page.add_init_script("localStorage.setItem('worldwalker.graphics.v1','auto')")
    page.reload()
    page.locator('#mobile-bottom-nav [data-mobile-view="map"]').click()
    page.wait_for_selector('.atlas-geography')
    assert page.locator('.atlas-scenery').count()==0
    assert page.locator('select[data-graphics-quality]').count()==1
    before=copy.deepcopy(game.state)
    page.locator('select[data-graphics-quality]').select_option('high')
    page.wait_for_selector('.atlas-3d-ready',timeout=45000)
    assert page.evaluate("localStorage.getItem('worldwalker.graphics.v1')")=='high'
    page.locator('select[data-graphics-quality]').select_option('low')
    page.wait_for_selector('.atlas-scenery',state='detached')
    page.evaluate('WorldAtlas.zoom(2)')
    assert page.locator('.map-node').count()>3
    assert game.state==before and not calls
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert page.locator('link[href*="dream-worlds.css"]').count()==1


@pytest.mark.parametrize('world',['Naruto','One Piece','Bleach'])
def test_low_combat_keeps_targeting_and_avoids_heavy_fx(ui,world):
    from test_naruto_tactical import fresh
    from test_one_piece_tactical import game as pirate
    from test_bleach_tactical import game as shinigami
    page,game,calls=ui
    fixture={'Naruto':fresh,'One Piece':pirate,'Bleach':shinigami}[world]()
    game.state=fixture.state
    game.autosave=lambda *a,**kw:None
    fetched=[]
    page.on('request',lambda r:fetched.append(r.url))
    page.goto(page.url.split('/?')[0].rstrip('/')+'/tactical-preview/designs/campaign.html')
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_selector('.piece')
    assert page.locator('select[data-graphics-quality]').input_value()=='low'
    assert page.evaluate("document.querySelector('#fx').width<=768")
    before=copy.deepcopy(game.state)
    page.locator('#attack').click()
    page.locator('#pieces .piece.enemy').first.click()
    assert page.locator('#confirm').is_enabled()
    assert page.locator('#tiles [data-key="3,2"]').evaluate("e=>e.classList.contains('target-area')")
    assert game.state==before
    # Drawing a frozen outcome in low mode neither downloads sheets nor applies gameplay.
    page.evaluate("""async()=>{fx.forcedReduced=true;await fx.play({id:'qa',origin:{x:2,y:2},aim:{x:3,y:2},cells:['3,2'],element:'fire',shape:'single',effect:{asset:'fireball',delivery:'projectile'},hits:[]});}""")
    assert not any('unity-attack-library' in u for u in fetched)
    assert game.state==before and not calls
    # An unchanged poll must not reconstruct the board/portraits.
    page.evaluate("window.__piece=document.querySelector('.piece .avatar'); refresh()")
    page.wait_for_function('!refreshInFlight')
    assert page.evaluate("window.__piece===document.querySelector('.piece .avatar')")
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    revision=page.evaluate('view.board.revision')
    page.locator('#confirm').click()
    page.wait_for_function('(revision)=>!busy&&view.board.revision>revision',arg=revision)
    assert page.locator('#hint').inner_text()=='Command resolved.'
    assert not any('unity-attack-library' in u for u in fetched)
    assert game.state!=before


def test_high_combat_loads_real_effect_from_campaign_url(ui):
    from test_naruto_tactical import fresh
    page,game,calls=ui
    game.state=fresh().state
    game.autosave=lambda *a,**kw:None
    page.goto(page.url.split('/?')[0].rstrip('/')+'/tactical-preview/designs/campaign.html')
    page.wait_for_selector('.piece')
    page.locator('select[data-graphics-quality]').select_option('high')
    before=copy.deepcopy(game.state)
    page.evaluate("""async()=>{await fx.play({id:'qa-high',origin:{x:2,y:2},aim:{x:3,y:2},cells:['3,2'],element:'fire',shape:'single',effect:{asset:'fireball',delivery:'projectile'},hits:[]});}""")
    assert page.locator('#fx').get_attribute('data-renderer')=='Unity', page.evaluate("({dataset:{...document.querySelector('#fx').dataset},forced:fx.forcedReduced,media:fx.media.matches,hidden:document.hidden})")
    assert not page.locator('#fx').get_attribute('data-asset-error')
    assert game.state==before and not calls
