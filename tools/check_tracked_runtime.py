"""Fail CI if local runtime data or signing keys enter the source manifest."""
from pathlib import PurePosixPath
import subprocess

def forbidden(path):
    parts=PurePosixPath(path.replace('\\','/')).parts
    return '.build-test-data' in parts or PurePosixPath(path).name == 'friend_server_secret.txt'

def main():
    paths=subprocess.check_output(['git','ls-files','-z'],text=True).split('\0')
    bad=[p for p in paths if p and forbidden(p)]
    if bad:
        raise SystemExit('Remove tracked runtime data/signing keys: '+', '.join(bad))
    print('Tracked runtime-data check passed.')

if __name__=='__main__': main()
