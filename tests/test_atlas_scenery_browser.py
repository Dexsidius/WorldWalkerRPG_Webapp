"""Actual HTTP module loading, rendering, ownership repaint and safe fallback."""
import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from check_reliability_browser import browser, ui

@pytest.mark.parametrize('world,width',[('Naruto',1366),('One Piece',1366),('One Piece',390)])
def test_scenery_keeps_campaign_and_map_controls(ui,world,width):
    from worlds import WORLD_DATA
    page,game,calls=ui
    game.state.update(world=world,location=WORLD_DATA[world]['map'][0][0])
    page.add_init_script("localStorage.setItem('worldwalker.graphics.v1','high')")
    page.evaluate("localStorage.setItem('worldwalker.graphics.v1','high')")
    page.reload()
    page.wait_for_selector('#workspace-map-tab')
    page.locator('#workspace-map-tab').click()
    page.wait_for_selector('.atlas-3d-ready',timeout=45000)
    page.set_viewport_size({'width':width,'height':844})
    if width<800:
        page.locator('#mobile-bottom-nav [data-mobile-view="map"]').click()
    before=copy.deepcopy(game.state)
    page.evaluate('WorldAtlas.zoom(2)')
    page.wait_for_function("document.querySelector('.atlas-plane')._atlasScenery.stats().zoom>=2")
    assert page.locator('.atlas-scenery').count()==1
    assert page.locator('.map-node').count()>3
    assert game.state==before and not calls
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')

def test_context_loss_restores_vector_atlas(ui):
    page,game,_=ui
    game.state.update(world='Naruto',location='Konohagakure')
    page.evaluate("localStorage.setItem('worldwalker.graphics.v1','high')")
    page.reload()
    page.locator('#workspace-map-tab').click()
    page.wait_for_selector('.atlas-3d-ready',timeout=45000)
    page.evaluate("document.querySelector('.atlas-scenery').dispatchEvent(new Event('webglcontextlost',{cancelable:true}))")
    assert page.locator('.atlas-3d-ready').count()==0
    assert page.locator('.atlas-geography').count()==1
    assert page.locator('.map-node').count()>0

def test_country_repaint_uses_changed_atlas_without_mutating_input(ui):
    from world_atlas import base_atlas
    page,game,_=ui
    game.state.update(world='Naruto',location='Konohagakure')
    page.evaluate("localStorage.setItem('worldwalker.graphics.v1','high')")
    page.reload()
    page.locator('#workspace-map-tab').click()
    page.wait_for_selector('.atlas-3d-ready',timeout=45000)
    atlas=copy.deepcopy(base_atlas('Naruto'))
    for cell in atlas['cells'][:40]:cell['owner']='Test territory'
    result=page.evaluate('''atlas=>{const before=JSON.stringify(atlas);const p=document.querySelector('.atlas-plane');
      const result=WorldAtlas.render(p,atlas,'repaint-test');return {unchanged:JSON.stringify(atlas)===before,owners:result.owners};}''',atlas)
    page.wait_for_function("document.querySelectorAll('.atlas-scenery').length===1 && document.querySelector('.atlas-3d-ready')!==null",timeout=45000)
    assert result['unchanged'] and 'Test territory' in result['owners']
