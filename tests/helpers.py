from pathlib import Path
import json, sys, tempfile, shutil
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'app'))
from engine import Engine
class Fixture:
    def __init__(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.base=self.root/'installer'; self.base.mkdir()
        for name in ('profile.json','mod-audit.json','graphics','web'):
            p=BASE/name
            if p.is_dir(): shutil.copytree(p,self.base/name)
            else: shutil.copy2(p,self.base/name)
        (self.base/'README.md').write_text('public code only',encoding='utf-8')
        (self.base/'publish-allowlist.json').write_text(json.dumps({'files':['README.md','profile.json']}),encoding='utf-8')
        self.game=self.root/'game'; self.game.mkdir(); (self.game/'LEGOStarWarsSaga.exe').write_bytes(b'MZ'+b'\x00'*126)
        for n in ('CHARS','STUFF','LEVELS'):
            (self.game/n).mkdir(); (self.game/n/'vanilla.txt').write_text('vanilla\n',encoding='utf-8')
        self.engine=Engine(self.base); self.selections={}
    def add(self,module,files,roots=None):
        p=self.root/(module+'-'+str(len(self.selections)));p.mkdir()
        for rel,data in files.items():
            f=p/rel; f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data if isinstance(data,bytes) else data.encode())
        source=self.engine.import_source(str(p),log=lambda x:None)
        self.selections[module]={'source_id':source['id'],'enabled':True,'confirmed':True,'roots':roots or source['roots']}
        return source
    def settings(self,**options):
        return {'game':str(self.game),'selections':self.selections,'options':{'clean_target_confirmed':True,'prepared_confirmed':True,**options},'decisions':{}}
    def plan(self,**opts): return self.engine.make_plan(self.settings(**opts),log=lambda x:None)
    def close(self): self.tmp.cleanup()
