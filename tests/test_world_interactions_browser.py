"""Shared world themes must not interfere with controls or map positioning."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from check_reliability_browser import browser, ui

@pytest.mark.parametrize('world,cursor',[
 ('Naruto','naruto-kunai'),('One Piece','one-piece-strawhat'),
 ('Bleach','bleach-zanpakuto'),('Jujutsu Kaisen','jjk-sukuna'),
 ('Hunter x Hunter','hunter-license'),('Overgeared','satisfy-blade'),
 ('Solo Max-Level Newbie','system-pointer'),('Reincarnated as a Slime','slime-pointer'),
 ('Custom World','world-crystal')])
def test_theme_and_cursor_assets(ui,world,cursor):
 page,game,calls=ui
 page.evaluate('(world)=>document.body.dataset.world=world',world)
 page.wait_for_function("getComputedStyle(document.body).getPropertyValue('--ui-time').trim()!==''")
 result=page.evaluate('''async()=>{
 const b=document.querySelector('#btn-advance'),css=getComputedStyle(b);
 const cursor=css.cursor,url=cursor.match(/url\\(["']?([^"')]+)/)?.[1];
 const img=new Image();img.src=url;await img.decode();
 return {cursor,width:img.naturalWidth,height:img.naturalHeight};}''')
 assert cursor in result['cursor']
 assert 0<result['width']<=48 and 0<result['height']<=48
 assert not calls

def test_reduced_motion_and_disabled_states(ui):
 page,game,calls=ui
 page.emulate_media(reduced_motion='reduce')
 page.evaluate("document.body.dataset.world='One Piece'")
 page.wait_for_function("getComputedStyle(document.querySelector('#btn-advance')).transitionDuration==='0s'")
 button=page.get_by_role('button',name='GAME',exact=True)
 button.evaluate('e=>e.disabled=true')
 button.hover()
 assert button.evaluate("e=>getComputedStyle(e).cursor")=='not-allowed'
 assert not calls

def test_modal_open_close_and_mobile_layout(ui):
 page,game,calls=ui
 page.set_viewport_size({'width':390,'height':844})
 page.get_by_role('button',name='HELP',exact=True).click()
 page.locator('[data-action="help"]').click()
 page.wait_for_selector('.modal-backdrop.open')
 modal=page.locator('.modal-backdrop.open').first
 modal.locator('.modal-close').first.click()
 page.wait_for_function("!document.querySelector('.modal-backdrop.open')")
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
 assert not calls
