"""OS protocol entry. Hand off NXM in memory to the authenticated loopback server.
No signed URLs in files or console logs. Does not download or execute mods itself.
"""
import json
import re
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from nexus import parse_nxm
BASE=Path(__file__).resolve().parent.parent

def main():
    if len(sys.argv)!=2: return 2
    profile=json.loads((BASE/'profile.json').read_text(encoding='utf-8'))
    try: parse_nxm(sys.argv[1],{m['nexus']['mod_id'] for m in profile['modules'] if m.get('nexus')})
    except Exception: return 2
    connection=BASE/'.local'/'connection.json'; started=False
    for _ in range(30):
        try:
            config=json.loads(connection.read_text(encoding='utf-8')); origin=config['origin']
            if not re.fullmatch(r'http://127\.0\.0\.1:\d{1,5}',origin): return 2
            token=urllib.parse.urlsplit(config['url']).fragment
            if not re.fullmatch(r'[a-zA-Z0-9_-]{20,100}',token): return 2
            request=urllib.request.Request(origin+'/api/nxm/receive',data=json.dumps({'url':sys.argv[1]}).encode(),
                        headers={'X-TCS-Token':token,'Content-Type':'application/json'},method='POST')
            # No HTTP redirects: a loopback protocol handoff may not leave this process.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*args,**kwargs): return None
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=4) as response:
                return 0 if response.status==200 else 1
        except Exception:
            if not started:
                subprocess.Popen([sys.executable,str(BASE/'app'/'server.py')],cwd=str(BASE),shell=False)
                started=True
            time.sleep(1)
    return 1
if __name__=='__main__': raise SystemExit(main())
