"""Build, verify and zip BOTH Windows editions from the same clean commit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def run(*args, **kwargs):
    return subprocess.run(args,cwd=ROOT,check=True,**kwargs)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'dist-editions')
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    run('git','diff','--exit-code','HEAD','--','.')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    sys.path.insert(0,str(ROOT/'backend'))
    from build_info import BUILD_ID
    from worlds import APP_VERSION
    pair=[]
    for edition,name in [('main','WorldwalkerRPG'),('offline','WorldwalkerOfflinePrototype')]:
        env={**os.environ,'WORLDWALKER_BUILD_EDITION':edition,'WORLDWALKER_MODE':edition}
        run(sys.executable,'-m','PyInstaller','--noconfirm','--clean','WorldwalkerRPG.spec',
            '--distpath',str(output/edition),'--workpath',str(output/'build'/edition),env=env)
        folder=output/edition/name;exe=folder/(name+'.exe')
        assert exe.read_bytes()[:2]==b'MZ'
        # Verify every shipped frontend and artwork file against this checkout.
        hashes={}
        for tree in ('frontend','assets'):
            for source in sorted((ROOT/tree).rglob('*')):
                if not source.is_file() or '__pycache__' in source.parts:continue
                relative=source.relative_to(ROOT);packaged=folder/'_internal'/relative
                digest=hashlib.sha256(source.read_bytes()).hexdigest()
                assert packaged.is_file() and hashlib.sha256(packaged.read_bytes()).hexdigest()==digest, f'Stale/missing file: {relative}'
                hashes[str(relative).replace('\\','/')]=digest
        with tempfile.TemporaryDirectory(prefix='worldwalker-'+edition+'-') as data:
            run(str(exe),'--self-test',env={**env,'WORLDWALKER_DATA_DIR':data},timeout=120)
        shutil.copytree(ROOT/'music',folder/'music',dirs_exist_ok=True)
        for doc in ('SHARED_EDITIONS.md','OFFLINE_README.md','PHONE_PLAY_README.txt'):
            shutil.copy2(ROOT/doc,folder/doc)
        (folder/'Start Phone Mode.bat').write_text('@echo off\nstart "" "%~dp0'+name+'.exe" --lan\n',encoding='utf-8')
        manifest={'edition':edition,'source_commit':commit,'version':APP_VERSION,'build_id':BUILD_ID,
                  'entry_point':name+'.exe','packaged_self_test':'passed','shared_file_hashes':hashes}
        (folder/'BUILD_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        path=Path(shutil.make_archive(str(output/f'Worldwalker-{edition}-{BUILD_ID}-Windows'),'zip',folder.parent,folder.name))
        pair.append({'edition':edition,'source_commit':commit,'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    assert len({p['source_commit'] for p in pair})==1
    (output/'RELEASE_PAIR.json').write_text(json.dumps({'build_id':BUILD_ID,'packages':pair},indent=2),encoding='utf-8')
    print(json.dumps(pair,indent=2))

if __name__=='__main__':main()
