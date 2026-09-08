"""Fresh processes prove offline settings cannot leak into the main edition."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('mode', ['main','offline'])
def test_edition_boot_contract(tmp_path,mode):
    code='''
import json
from app import app,game,ACCOUNTS_ENABLED
from util import APP_DIR_NAME
from living_adventures import action_list
c=app.test_client()
html=c.get('/').get_data(as_text=True)
print(json.dumps(dict(mode=game.offline_mode(),provider=game.ai.provider,folder=APP_DIR_NAME,
    ui='src="/js/offline-play.js?' in html, creation=c.get('/api/offline/creation').status_code,
    accounts=ACCOUNTS_ENABLED)))
'''
    env={**os.environ,'WORLDWALKER_MODE':mode,'WORLDWALKER_DATA_DIR':str(tmp_path),'PYTHONPATH':str(ROOT/'backend'), 'WORLDWALKER_ACCOUNTS_ENABLED':'0'}
    result=json.loads(subprocess.check_output([sys.executable,'-c',code],cwd=ROOT,env=env,text=True))
    offline=mode=='offline'
    assert result['mode']==offline and result['ui']==offline
    assert (result['provider']=='offline')==offline
    assert result['folder']==('WorldwalkerRPGOfflinePrototype' if offline else 'WorldwalkerRPG')
    assert result['creation']==(200 if offline else 404)

def test_main_login_page_preserved(tmp_path):
    env={**os.environ,'WORLDWALKER_MODE':'main','WORLDWALKER_ACCOUNTS_ENABLED':'1',
         'WORLDWALKER_DATA_DIR':str(tmp_path),'PYTHONPATH':str(ROOT/'backend')}
    code="from app import app; c=app.test_client(); assert c.get('/').status_code==200; assert c.get('/api/auth/session').status_code==200"
    subprocess.run([sys.executable,'-c',code],env=env,cwd=ROOT,check=True)

def test_every_action_has_reviewed_edition_support():
    from app import app
    catalog=json.loads((ROOT/'assets/data/edition_support.json').read_text(encoding='utf-8'))['routes']
    actual={r.rule for r in app.url_map.iter_rules() if 'POST' in r.methods and r.rule.startswith('/api/')}
    assert set(catalog)==actual, f'Review offline support for added/removed routes: {set(catalog)^actual}'
    for path,row in catalog.items():
        assert row['support'] in {'shared','main-only','offline-only'} and row['offline_behavior'],path
