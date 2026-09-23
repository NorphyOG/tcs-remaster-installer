"""Offline, fixed-operation UAC worker. No network/download/executable patching."""
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from engine import Engine, digest, jsonwrite, within
from safety import BuildError, no_links
from preparation import commit_preparation, restore_preparation
BASE=Path(__file__).resolve().parent.parent

def main():
    if len(sys.argv)!=3: return 2
    request=no_links(Path(sys.argv[1]))
    if not within(request,BASE/'.local'/'elevated') or not re.fullmatch(r'[a-f0-9]{32}\.json',request.name): return 2
    if digest(request)!=sys.argv[2]: return 2
    data=json.loads(request.read_text(encoding='utf-8')); result=request.with_suffix('.result.json')
    if data.get('result')!=str(result): return 2
    try:
        engine=Engine(BASE); p=data['payload']; action=data['action']
        if action=='prepare_commit': output=commit_preparation(Path(p['manifest']),engine.local,lambda _:None)
        elif action=='prepare_restore': output=restore_preparation(p['game'],lambda _:None)
        elif action=='install':
            pid=p['plan_id']
            if not re.fullmatch(r'[a-f0-9]{32}',pid): raise BuildError('Ungültige Plan-ID.')
            path=engine.local/'plans'/(pid+'.json')
            if digest(path)!=p['sha256']: raise BuildError('Dateiplan verändert.')
            plan=json.loads(path.read_text(encoding='utf-8'))
            output=engine.install(plan,lambda _:None)
        elif action=='restore': output=engine.restore(p['game'],lambda _:None)
        else: raise BuildError('Unzulässiger Schreibauftrag.')
        jsonwrite(result,{'result':output})
    except Exception as exc:
        jsonwrite(result,{'error':str(exc)})
    return 0
if __name__=='__main__': raise SystemExit(main())
