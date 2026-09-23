"""Persistent stage progress, NOT an estimate of remaining time.
Only explicit successful boundaries complete a stage. Unknown totals stay unknown.
"""
from __future__ import annotations
import copy
import json
import threading
from pathlib import Path
from engine import jsonwrite
from safety import no_links

DEFINITIONS = [
    ('prepare', 'Spiel vorbereiten', 'Originaldaten prüfen, entpacken und sichern'),
    ('downloads', 'Modarchive übernehmen', 'Fertige Downloads erkennen und sicher entpacken'),
    ('mapping', 'Varianten zuordnen', 'Abhängigkeiten, Versionen und Classic-Icons prüfen'),
    ('compare', 'Dateien zusammenführen', 'Dateiplan und offene Konflikte prüfen'),
    ('install', 'Mods installieren', 'Betroffene Originale sichern und Moddateien einsetzen'),
    ('verify', 'Installation prüfen', 'Installierte Dateien, EXE und Startziel kontrollieren'),
    ('launch', 'Spiel starten / testen', 'Startbefehl und Spieltest getrennt bestätigen'),
]
STATES = {'pending', 'running', 'waiting', 'done', 'error', 'paused'}

class StepTracker:
    def __init__(self, local: Path):
        self.path=no_links(local/'steps.json');self.lock=threading.RLock()
        self.data={'schema':1,'stages':{key:{'status':'pending','detail':desc,'progress':None}
                                    for key,_,desc in DEFINITIONS}}
        if self.path.is_file():
            try:
                old=json.loads(self.path.read_text(encoding='utf-8'))
                if old.get('schema')==1:
                    for key,_,_ in DEFINITIONS:
                        v=old.get('stages',{}).get(key,{})
                        if isinstance(v,dict) and v.get('status') in STATES:
                            self.data['stages'][key].update({k:v[k] for k in ('status','detail','progress') if k in v})
                            if v.get('status')=='running':self.data['stages'][key]['status']='paused'
            except (OSError,ValueError,TypeError,AttributeError):pass
    def update(self,key,status=None,detail=None,progress=None,keep_progress=False):
        if key not in self.data['stages']:return
        with self.lock:
            v=self.data['stages'][key]
            if status:
                if status not in STATES:raise ValueError('Invalid stage status')
                v['status']=status
            if detail is not None:v['detail']=str(detail)[:500]
            if not keep_progress:v['progress']=progress
            jsonwrite(self.path,self.data)
    def public(self):
        with self.lock:
            rows=[]
            for key,title,_ in DEFINITIONS:
                v=copy.deepcopy(self.data['stages'][key]);v.update(id=key,title=title)
                rows.append(v)
            return {'stages':rows,'completed':sum(r['status']=='done' for r in rows),
                    'total':len(rows),'time_estimate':False}
    def reset(self, keys=None):
        keys=keys or [k for k,_,_ in DEFINITIONS]
        for k,_,desc in DEFINITIONS:
            if k in keys:self.update(k,'pending',desc)

def stage(log,key,status='running',detail=None,done=None,total=None,unit='Dateien'):
    fn=getattr(log,'stage',None)
    if callable(fn):fn(key,status,detail,done,total,unit)
