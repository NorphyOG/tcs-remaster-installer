"""Local browser wizard. Loopback only; per-run token + origin/host checks.
No external telemetry, no execution of imported mod code, no shell command endpoint.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import argparse
import base64
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from diagnostics import Cancelled, error_record, redact
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from engine import Engine, describe_game, jsonwrite, no_links, APP_ID, EXE, META
from safety import BuildError, MAX_ARCHIVE, find_7zip

BASE=Path(__file__).resolve().parent.parent

PICKER_SCRIPT=r'''
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.Opacity = 0
$owner.Show()
try {
    if ($env:TCS_PICKER_KIND -eq 'folder') {
        $d = New-Object System.Windows.Forms.FolderBrowserDialog
        $d.Description = 'Ordner auswählen'
        $d.ShowNewFolderButton = $true
        if ($d.ShowDialog($owner) -eq 'OK') { $r = $d.SelectedPath } else { $r = '' }
    } else {
        $d = New-Object System.Windows.Forms.OpenFileDialog
        $d.Title = 'Zusammengeführte Patchdatei auswählen'
        $d.CheckFileExists = $true
        if ($d.ShowDialog($owner) -eq 'OK') { $r = $d.FileName } else { $r = '' }
    }
    [Console]::Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($r)))
} finally { $owner.Close(); $owner.Dispose() }
'''

def picker(kind:str):
    if os.name!='nt': raise BuildError('Native Ordnerauswahl ist für Windows vorgesehen. Auf diesem System den vollständigen Pfad in das Feld einfügen.')
    if kind not in ('folder','file'): raise BuildError('Unbekannter Dialog.')
    env=dict(os.environ); env['TCS_PICKER_KIND']=kind
    encoded=base64.b64encode(PICKER_SCRIPT.encode('utf-16le')).decode('ascii')
    r=subprocess.run(['powershell.exe','-NoProfile','-STA','-EncodedCommand',encoded],capture_output=True,timeout=300,env=env,creationflags=0x08000000)
    if r.returncode: raise BuildError('Windows-Dateiauswahl konnte nicht geöffnet werden. Pfad manuell eingeben.')
    return base64.b64decode(r.stdout.strip()).decode('utf-8')

def steam_candidates():
    bases=[]
    if os.name=='nt':
        import winreg
        for hive,key,name in [(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam','SteamPath'),(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\WOW6432Node\Valve\Steam','InstallPath')]:
            try:
                with winreg.OpenKey(hive,key) as k: bases.append(Path(winreg.QueryValueEx(k,name)[0]))
            except OSError: pass
        bases += [Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Steam']
    allbases=list(bases)
    for b in bases:
        vdf=b/'steamapps'/'libraryfolders.vdf'
        if vdf.is_file():
            try:
                for val in re.findall(r'"path"\s+"([^"\r\n]+)"',vdf.read_text(encoding='utf-8')):
                    allbases.append(Path(val.replace('\\\\','\\')))
            except OSError: pass
    found=[]
    for b in allbases:
        steamapps=b/'steamapps'; manifest=steamapps/'appmanifest_32440.acf'
        names=['Lego Star Wars Saga','LEGO Star Wars - The Complete Saga']
        if manifest.is_file():
            text=manifest.read_text(encoding='utf-8',errors='replace')
            names += re.findall(r'"installdir"\s+"([^"\r\n]+)"',text)
        for name in names:
            p=steamapps/'common'/name
            if p.is_dir() and str(p) not in found:
                try: describe_game(str(p)); found.append(str(p))
                except BuildError: pass
    return found

class JobReporter:
    def __init__(self,app,job):
        self.app=app;self.job=job;self.last_progress=0;self.active_stage=None
    def __call__(self,message):
        stamp=datetime.now().strftime('%H:%M:%S')
        value=redact(message,self.app.private_paths(),self.app.private_secrets())
        with self.app.job_lock:
            self.job['logs'].append(stamp+' · '+value)
            self.job['logs']=self.job['logs'][-200:]
            self.app.save_job()
    def stage(self,key,status,detail,done=None,total=None,unit='Dateien'):
        self.active_stage=key if status=='running' else None
        p={'done':done,'total':total,'unit':unit} if done is not None else None
        self.app.steps.update(key,status,detail,p)
        self.job['stage']=key
    def phase(self,key,label):
        # Explicit phase routing. Finishing a tool call never completes a stage.
        routes={'inspect':'prepare','unpack_mod':'downloads','import_mod':'downloads',
                'download_mods':'downloads','compare':'compare','install':'install','verify_install':'verify'}
        if key in routes:self.active_stage=routes[key]
        if self.active_stage:
            self.app.steps.update(self.active_stage,'running',redact(label,self.app.private_paths(),self.app.private_secrets()))
            self.job['stage']=self.active_stage
        with self.app.job_lock:
            self.job.update(phase=key,phase_label=label,progress=None)
        self(label)
    def progress(self,done,total,unit):
        now=time.monotonic()
        if now-self.last_progress<0.7 and (total is None or done<total): return
        self.last_progress=now
        with self.app.job_lock:
            self.job['progress']={'done':done,'total':total,'unit':unit}
            if self.active_stage:self.app.steps.update(self.active_stage,progress=self.job['progress'],detail=self.job.get('phase_label'))
            self.app.save_job()
    def original_filter(self, archive, excluded):
        # Bounded diagnostic summary, no payloads or absolute file paths. Entries
        # are informational only and never authorise an installation operation.
        sample = [redact(r['path'], self.app.private_paths(), self.app.private_secrets())
                  for r in excluded[:20]]
        with self.app.job_lock:
            data = self.job.setdefault('original_filter', {'excluded_count': 0, 'samples': [],
                                                          'archives_checked': 0, 'policy': 'original-data-only-v1'})
            data['archives_checked'] += 1
            data['excluded_count'] += len(excluded)
            data['samples'] = (data['samples'] + sample)[:20]
            self.app.save_job()
    def pak_check(self, archive, info):
        with self.app.job_lock:
            data = self.job.setdefault('pak_checks', {'archives_checked': 0,
                       'entries': 0, 'short_entries': 0, 'zero_entries': 0,
                       'native_archives': 0, 'cached_archives': 0, 'last_archive': ''})
            data['archives_checked'] += 1
            for name in ('entries', 'short_entries', 'zero_entries'):
                data[name] += int(info.get(name, 0))
            data['native_archives'] += int(info.get('method') == 'native-raw')
            data['cached_archives'] += int(info.get('method') == 'verified-cache')
            data['last_archive'] = redact(archive, self.app.private_paths(), self.app.private_secrets())[:220]
            self.app.save_job()
    def check_cancelled(self):
        if self.app.cancel_event.is_set():
            raise Cancelled('Automatik angehalten. Vollständig geprüfte Zwischenschritte bleiben erhalten. Mit „Erneut versuchen / fortsetzen“ weiterarbeiten.')


class App:
    def __init__(self,base:Path=BASE):
        self.engine=Engine(base); self.token=secrets.token_urlsafe(32); self.origin=''
        self.job={'id':'','running':False,'logs':[],'result':None,'error':None,'phase':'idle','phase_label':'Bereit','status':'idle'}
        self.job_lock=threading.RLock();self.cancel_event=threading.Event()
        self.logs=no_links(self.engine.local/'logs');self.logs.mkdir(exist_ok=True)
        self.last_error=None
        previous=self.logs/'last-error.json'
        if previous.is_file():
            try:self.last_error=json.loads(previous.read_text(encoding='utf-8'))
            except (OSError,ValueError):pass
        self.export_path=None
        from steps import StepTracker
        self.steps=StepTracker(self.engine.local)
        from workflow import Workflow
        self.workflow=Workflow(self)
        old=self.logs/'last-job.json'
        if old.is_file():
            try:
                prior=json.loads(old.read_text(encoding='utf-8'))
                if isinstance(prior,dict):
                    self.job={**self.job,**prior,'running':False,'result':None}
                    if prior.get('running'):
                        self.job.update(status='interrupted',error='Der vorherige Assistent wurde während eines Arbeitsschritts geschlossen. Automatik bleibt pausiert. Erneut starten prüft vorhandene Zwischenstände.',phase_label='Vorheriger Lauf unterbrochen')
            except (OSError,ValueError):pass
        # Migration from 0.3.x: restore an actually prepared structure, not an old
        # boolean checkbox. No hashing of the whole installation on UI startup.
        saved_game=self.engine.state.get('game')
        if saved_game:
            try:
                info=describe_game(saved_game)
                if info['prepared_structure'] and not info['active_data_archives']:
                    self.steps.update('prepare','done','Vorhandene vorbereitete Spielstruktur erkannt; nicht erneut entpacken')
            except (OSError,BuildError,ValueError):pass
        self.workflow.refresh_inventory(JobReporter(self,self.job))
    def private_paths(self):
        return [(str(self.engine.base),'[INSTALLER]'),(self.engine.state.get('game',''),'[SPIEL]'),
                (self.engine.state.get('automation',{}).get('watch_folder',''),'[DOWNLOADS]'),(str(Path.home()),'[BENUTZER]')]
    def private_secrets(self):
        return [self.token,self.workflow.nexus._key] if hasattr(self,'workflow') else [self.token]
    def save_job(self):
        # No response bodies, signed URLs, file plans or API credentials on disk.
        snapshot={k:v for k,v in self.job.items() if k not in ('result',)}
        jsonwrite(self.logs/'last-job.json',snapshot)
    def diagnostic(self):
        with self.job_lock:
            return {'installer_version':'0.4.0','python':sys.version.split()[0],'platform':os.name,
                    'job':{k:v for k,v in self.job.items() if k!='result'},'last_error':self.last_error,
                    'steps':self.steps.public(),'inventory':self.workflow.inventory(),
                    'game_tested':False,'note':'Keine automatische Übertragung. Keine Spiel- oder Moddateien enthalten.'}
    def busy(self):
        if self.job['running']: raise BuildError('Ein Arbeitsschritt läuft bereits. Einstellungen sind bis zum Abschluss gesperrt.')
    def request_stop(self):
        # No engine lock: a read/download may be executing. A commit finishes safely.
        self.cancel_event.set()
        with self.workflow.lock:
            self.workflow.watch_paused=True
            self.engine.state['automation']['armed']=False
            self.workflow.message='Stopp angefordert. Downloads/Prüfungen halten am nächsten sicheren Punkt; ein laufender Schreibvorgang wird sicher beendet.'
        if not self.job['running']:
            self.engine.save()
        return {'stopped':True,'note':self.workflow.message}
    def start_job(self,func,action='operation'):
        with self.job_lock:
            self.busy();self.cancel_event.clear()
            job={'id':uuid.uuid4().hex[:12],'action':action,'running':True,'logs':[],'result':None,'error':None,
                 'phase':'starting','phase_label':'Arbeitsschritt wird gestartet','status':'running',
                 'started':datetime.now(timezone.utc).isoformat(),'progress':None}
            self.job=job;self.save_job()
        log=JobReporter(self,job)
        def run():
            try:
                log('Lokaler Arbeitsschritt gestartet. Fortschritt bleibt in dieser Sitzung sichtbar.')
                with self.engine.lock: result=func(log)
                with self.job_lock:
                    job['result']=result
                    job['status']='waiting' if isinstance(result,dict) and result.get('waiting') else 'success'
                    if isinstance(result,dict) and result.get('status','').startswith('INSTALLED'):
                        job.update(phase='installed',phase_label='Dateien installiert · Spieltest steht aus',progress=None)
                    if self.last_error and self.last_error.get('action')==action:
                        self.last_error['resolved']=True;jsonwrite(self.logs/'last-error.json',self.last_error)
            except Exception as exc:
                with self.job_lock:
                    record=error_record(exc,job,self.private_paths(),self.private_secrets())
                    self.last_error=record
                    job.update(error=record['message'],error_id=record['id'],recovery=record['recovery'],status='cancelled' if record['cancelled'] else 'error')
                    jsonwrite(self.logs/(job['id']+'.json'),record)
                    jsonwrite(self.logs/'last-error.json',record)
                stage_key=job.get('stage')
                if stage_key:self.steps.update(stage_key,'paused' if record['cancelled'] else 'error',record['message'])
                self.workflow.on_failure(record['message'],action)
                # Avoid printing raw exception URLs / credentials in the console.
                print(record['traceback'],flush=True)
            finally:
                with self.job_lock:
                    job['running']=False;job['finished']=datetime.now(timezone.utc).isoformat();self.save_job()
                if self.cancel_event.is_set():
                    self.engine.state['automation']['armed']=False;self.engine.save()
        threading.Thread(target=run,daemon=True).start()
        return {'started':True,'id':job['id']}
    def public_state(self):
        with self.job_lock: job=dict(self.job)
        return {'profile':self.engine.profile,'state':self.engine.state,'sevenzip':bool(find_7zip()),
                'platform':os.name,'installer_version':'0.4.0','python_version':sys.version.split()[0],
                'can_install_on_platform':os.name=='nt','job':job,'has_plan':bool(self.engine.plan),
                'workflow':self.workflow.public(),'last_error':self.last_error,'steps':self.steps.public()}

class Handler(BaseHTTPRequestHandler):
    server_version='TCSLocal/0.4.0'
    def log_message(self,*args): pass
    @property
    def app(self): return self.server.app
    def send(self,data,status=200,mime='application/json; charset=utf-8',headers=None):
        body=json.dumps(data,ensure_ascii=False).encode() if mime.startswith('application/json') else data
        self.send_response(status); self.send_header('Content-Type',mime); self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer'); self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError): pass
    def auth(self):
        expected=self.app.origin.removeprefix('http://')
        if self.headers.get('Host')!=expected: return False
        origin=self.headers.get('Origin')
        if origin and origin!=self.app.origin: return False
        return secrets.compare_digest(self.headers.get('X-TCS-Token',''),self.app.token)
    def read_json(self):
        n=int(self.headers.get('Content-Length','0'))
        if n<0 or n>4*1024**2: raise BuildError('Anfrage zu groß.')
        if not self.headers.get('Content-Type','').startswith('application/json'): raise BuildError('JSON-Anfrage erwartet.')
        return json.loads(self.rfile.read(n))
    def do_OPTIONS(self): self.send({'error':'Cross-origin requests are disabled'},403)
    def do_GET(self):
        route=urllib.parse.urlparse(self.path).path
        if route.startswith('/api/'):
            if not self.auth(): return self.send({'error':'Sitzung fehlt oder Zugriff von fremder Seite. Assistent über STARTEN.cmd öffnen.'},403)
            try:
                if route=='/api/steps':return self.send(self.app.steps.public())
                if route=='/api/state': return self.send(self.app.public_state())
                if route=='/api/job': return self.send({**self.app.job,'steps':self.app.steps.public()})
                if route=='/api/diagnostics': return self.send(self.app.diagnostic())
                if route=='/api/plan': return self.send(self.app.engine.plan)
                if route=='/api/automation/status': return self.send(self.app.workflow.public())
                if route=='/api/audit':
                    p=self.app.engine.base/'mod-audit.json'
                    return self.send(json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {'items':[]})
                if route=='/api/download':
                    q=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query); kind=q.get('kind',[''])[0]
                    if kind=='diagnostics':
                        data=json.dumps(self.app.diagnostic(),ensure_ascii=False,indent=2).encode('utf-8');name='TCS-Diagnose-0.4.0.json'
                    elif kind=='report':
                        if not self.app.engine.plan: raise BuildError('Noch kein Bericht vorhanden.')
                        data=json.dumps(self.app.engine.plan,ensure_ascii=False,indent=2).encode('utf-8'); name='TCS-Pruefbericht.json'
                    elif kind=='installer':
                        p=self.app.export_path
                        if not p or not p.is_file(): raise BuildError('Installer zuerst exportieren.')
                        data=p.read_bytes(); name=p.name
                    else: raise BuildError('Unbekannter Download.')
                    return self.send(data,mime='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="{name}"'})
                return self.send({'error':'Nicht gefunden'},404)
            except Exception as e: return self.send({'error':str(e)},400)
        static={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/style.css':'style.css','/auto.js':'auto.js','/journey.js':'journey.js','/icon.svg':'icon.svg','/icon.png':'icon.png','/icon.ico':'icon.ico'}
        if route not in static: return self.send({'error':'Nicht gefunden'},404)
        p=self.app.engine.base/'web'/static[route]
        mime={'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8','svg':'image/svg+xml','png':'image/png','ico':'image/x-icon'}[p.suffix[1:]]
        self.send(p.read_bytes(),mime=mime)
    def do_POST(self):
        route=urllib.parse.urlparse(self.path).path
        if not self.auth(): return self.send({'error':'Nicht autorisiert.'},403)
        try:
            if route=='/api/upload':
                self.app.busy()
                if not self.headers.get('Content-Type','').startswith('application/octet-stream'): raise BuildError('Binärer Upload erwartet.')
                n=int(self.headers.get('Content-Length','0'))
                if n<=0 or n>MAX_ARCHIVE: raise BuildError('Archiv muss zwischen 1 Byte und 8 GiB groß sein.')
                name=urllib.parse.unquote(self.headers.get('X-TCS-Filename','mod.zip'))
                if len(name)>240 or any(ord(x)<32 for x in name): raise BuildError('Ungültiger Dateiname.')
                ext=Path(name).suffix.lower()
                if ext not in ('.zip','.7z','.rar'): raise BuildError('Nur ZIP, 7z und RAR hochladen; entpackte Ordner über die Ordnerauswahl hinzufügen.')
                target=self.app.engine.local/'imports'/(secrets.token_hex(12)+ext)
                if shutil.disk_usage(target.parent).free<n+256*1024**2: raise BuildError('Nicht genug Speicher für diesen lokalen Import.')
                self.connection.settimeout(180)
                try:
                    with target.open('xb') as f:
                        left=n
                        while left:
                            b=self.rfile.read(min(1024*1024,left))
                            if not b: raise BuildError('Upload wurde unterbrochen.')
                            f.write(b); left-=len(b)
                    module_id=self.headers.get('X-TCS-Module') or None
                    if module_id and module_id not in {m['id'] for m in self.app.engine.profile['modules']}:raise BuildError('Unbekanntes Rezeptmodul.')
                    def imported(log):
                        item=self.app.workflow.import_data(str(target),name,log,module_id)
                        return {**item,'workflow':self.app.workflow.maybe_install(log)}
                    return self.send(self.app.start_job(imported,action='import'))
                except Exception:
                    target.unlink(missing_ok=True); raise
            data=self.read_json()
            if not isinstance(data,dict): raise BuildError('JSON-Objekt erwartet.')
            if route=='/api/diagnostics/ack':
                self.app.last_error=None;(self.app.logs/'last-error.json').unlink(missing_ok=True)
                return self.send({'cleared':True})
            if route=='/api/defaults':
                from workflow import default_download_folder
                return self.send({'downloads':default_download_folder(),'games':steam_candidates()})
            if route=='/api/nxm/receive':
                return self.send(self.app.workflow.receive_nxm(data.get('url','')))
            if route=='/api/automation/settings':
                self.app.busy(); return self.send(self.app.workflow.configure(data))
            if route=='/api/automation/start':
                return self.send(self.app.start_job(lambda log:self.app.workflow.arm(data.get('confirmation'),log),action='automatic-install'))
            if route=='/api/automation/continue':
                if data.get('confirmation')!='CONTINUE': raise BuildError('Fortsetzen bitte bestätigen.')
                return self.send(self.app.start_job(lambda log:self.app.workflow.resume(log),action='automatic-install'))
            if route=='/api/automation/stop':
                return self.send(self.app.request_stop())
            if route=='/api/prepare':
                if data.get('confirmation')!='PREPARE': raise BuildError('Vorbereitung bitte ausdrücklich bestätigen.')
                if not self.app.engine.state['options'].get('clean_target_confirmed'): raise BuildError('Unveränderte Spielkopie zuerst bestätigen.')
                return self.send(self.app.start_job(lambda log:self.app.workflow.prepare(data.get('game',''),log),action='prepare'))
            if route=='/api/prepare/restore':
                if data.get('confirmation')!='RESTORE_PREPARATION': raise BuildError('Wiederherstellung bitte bestätigen.')
                return self.send(self.app.start_job(lambda log:self.app.workflow.restore(data.get('game',''),original=True,log=log)))
            if route=='/api/tools/quickbms':
                return self.send(self.app.start_job(lambda log:self.app.workflow.tools.import_quickbms(data.get('path',''))))
            if route=='/api/tools/sevenzip':
                self.app.workflow.tool_consent()
                return self.send(self.app.start_job(lambda log:{'path':self.app.workflow.tools.sevenzip(log)}))
            if route=='/api/open-download':
                module=next((m for m in self.app.engine.profile['modules'] if m['id']==data.get('module')),None)
                if not module:raise BuildError('Unbekannte Downloadkarte.')
                resolved=self.app.workflow.nexus.catalog.get(module['id'],{})
                url=resolved.get('download_page') or module['url']
                webbrowser.open(url)
                return self.send({'opened':True,'module':module['id']})
            if route=='/api/nexus/connect':
                self.app.busy(); return self.send(self.app.workflow.nexus.connect(data.get('key','')))
            if route=='/api/nexus/disconnect':
                self.app.busy(); return self.send(self.app.workflow.nexus.disconnect())
            if route=='/api/nexus/files':
                return self.send(self.app.start_job(lambda log:self.app.workflow.nexus.resolve(log)))
            if route=='/api/nexus/download':
                return self.send(self.app.start_job(lambda log:self.app.workflow.fetch_one(data.get('module',''),log)))
            if route=='/api/nexus/download-selected':
                return self.send(self.app.start_job(lambda log:self.app.workflow.fetch_selected(log)))
            if route=='/api/nxm/register':
                self.app.busy()
                from windows import register_nxm
                return self.send(register_nxm(self.app.engine.base,confirmation=data.get('confirmation')))
            if route=='/api/nxm/unregister':
                self.app.busy()
                from windows import unregister_nxm
                return self.send(unregister_nxm(self.app.engine.base))
            if route=='/api/shortcuts':
                self.app.busy()
                if data.get('confirmation')!='CREATE_SHORTCUTS': raise BuildError('Verknüpfungen bitte bestätigen.')
                from windows import create_shortcuts
                return self.send(create_shortcuts(self.app.engine.base,data.get('game','')))
            if route=='/api/picker':
                self.app.busy(); return self.send({'path':picker(data.get('kind','folder'))})
            if route=='/api/detect':
                self.app.busy(); return self.send({'paths':steam_candidates()})
            if route=='/api/game':
                self.app.busy(); result=describe_game(data.get('path',''))
                previous=self.app.engine.state.get('game')
                if previous!=result['path']:
                    self.app.steps.reset(['prepare','compare','install','verify','launch'])
                    self.app.engine.state.pop('readiness',None)
                    if result['active_install']:self.app.engine.state['installed_game']=result['path']
                    else:self.app.engine.state.pop('installed_game',None)
                self.app.engine.state['game']=result['path']; self.app.engine.save(); self.app.engine.plan=None
                if result['prepared_structure'] and not result['active_data_archives']:
                    self.app.steps.update('prepare','done','Lose Spieldaten vorhanden. Kein erneutes Entpacken nötig.')
                return self.send(result)
            if route=='/api/import':
                return self.send(self.app.start_job(lambda log:self.app.workflow.import_data(data.get('path',''),log=log)))
            if route=='/api/settings':
                self.app.busy()
                for key in ('game','baseline','selections','options','decisions'):
                    if key in data:
                        if key in ('game','baseline') and not isinstance(data[key],str): raise BuildError('Ein Ordnerpfad fehlt oder ist ungültig.')
                        if key in ('selections','options','decisions') and not isinstance(data[key],dict): raise BuildError('Einstellungen sind unvollständig; Seite neu laden.')
                        self.app.engine.state[key]=data[key]
                self.app.engine.save(); self.app.engine.plan=None; return self.send({'saved':True})
            if route=='/api/plan':
                return self.send(self.app.start_job(lambda log:self.app.engine.make_plan(data,log)))
            if route=='/api/build':
                p=self.app.engine.plan
                if not p or p['id']!=data.get('plan_id'): raise BuildError('Prüfbericht fehlt oder ist veraltet. Erneut prüfen.')
                return self.send(self.app.start_job(lambda log:self.app.engine.make_build(p,log)))
            if route=='/api/install':
                if os.name!='nt': raise BuildError('Installation im Browser-Assistenten ist auf Windows beschränkt. Kernlogik wird separat mit Testdateien geprüft.')
                p=self.app.engine.plan
                if not p or p['id']!=data.get('plan_id'): raise BuildError('Prüfbericht fehlt oder ist veraltet. Erneut prüfen.')
                if data.get('confirmation')!='INSTALL': raise BuildError('Installation muss ausdrücklich bestätigt werden.')
                return self.send(self.app.start_job(lambda log:self.app.workflow.install(p,log)))
            if route=='/api/restore':
                if data.get('confirmation')!='RESTORE': raise BuildError('Wiederherstellung bitte bestätigen.')
                return self.send(self.app.start_job(lambda log:self.app.workflow.restore(data.get('game',''),log=log)))
            if route=='/api/export':
                self.app.busy(); self.app.export_path=self.app.engine.export_installer(); return self.send({'name':self.app.export_path.name})
            if route=='/api/preview':
                p=self.app.engine.plan
                if not p: raise BuildError('Kein Prüfbericht vorhanden.')
                key=data.get('key'); row=next((r for r in p['records'] if r['key']==key),None)
                if not row: raise BuildError('Datei nicht in diesem Plan.')
                variants=[]
                for v in row['versions']:
                    item={'module':v['module'],'sha256':v['sha256'],'text':None}
                    if v['bytes']<=2*1024**2:
                        d=__import__('merge').decode(self.app.engine.blob(v['sha256']).read_bytes())
                        if d: item['text']=d[0][:100_000]
                    variants.append(item)
                proposal=row.get('merge_proposal'); text=None
                if proposal:
                    d=__import__('merge').decode(self.app.engine.blob(proposal['sha256']).read_bytes())
                    text=d[0][:100_000] if d else None
                return self.send({'path':row['path'],'variants':variants,'proposal':text,'max_display_chars':100000})
            if route=='/api/open-result':
                self.app.busy()
                kind=data.get('kind'); state=self.app.engine.state
                if kind=='game': target=Path(state.get('installed_game') or state.get('game',''))
                elif kind=='build': target=Path(state.get('last_build',{}).get('folder',''))
                elif kind=='installer': target=self.app.engine.base
                elif kind=='logs': target=self.app.logs
                else: raise BuildError('Unbekanntes Ziel.')
                if not target.is_absolute() or not target.is_dir(): raise BuildError('Zielordner fehlt.')
                if os.name=='nt': os.startfile(str(target))
                else: raise BuildError('Ordnerpfad: '+str(target))
                return self.send({'opened':str(target)})
            if route=='/api/verify':
                return self.send(self.app.start_job(lambda log:self.app.workflow.verify(log),action='verify'))
            if route=='/api/game-tested':
                self.app.busy()
                if data.get('confirmation')!='GAME_AND_MODS_TESTED':raise BuildError('Erfolgreichen Spiel- und Modtest ausdrücklich bestätigen.')
                r=self.app.engine.state.get('readiness',{})
                if not r.get('can_launch') or not r.get('launch_requested'):raise BuildError('Erst Installation prüfen und Spiel starten.')
                from safety import digest
                game=Path(r['game'])
                if digest(game/META/'journal.json')!=r['journal_sha256'] or digest(Path(r['exe']))!=r['exe_sha256']:
                    raise BuildError('Installation seit dem Start verändert. Erneut prüfen.')
                r['user_reported_game_test']=True;self.app.engine.save()
                self.app.steps.update('launch','done','Spiel und Mods vom Benutzer als funktionierend bestätigt (kein automatischer Test).')
                return self.send({'user_confirmed':True})
            if route=='/api/launch':
                self.app.busy()
                if os.name!='nt': raise BuildError('Spielstart ist nur für Windows vorgesehen.')
                game=self.app.engine.state.get('installed_game')
                if not game: raise BuildError('Kein vom Assistenten installierter Build vorhanden. Im Reloaded-Modus über Reloaded starten.')
                info=describe_game(game)
                if data.get('confirmation')!='LAUNCH': raise BuildError('Spielstart bestätigen.')
                def launch(log):
                    from readiness import launch_selected
                    result=launch_selected(self.app.engine.base,log)
                    saved=json.loads(self.app.engine.statefile.read_text(encoding='utf-8'))
                    self.app.engine.state['readiness']=saved.get('readiness');return result
                return self.send(self.app.start_job(launch,action='launch'))
            if route=='/api/shutdown':
                self.app.busy(); self.send({'closed':True}); threading.Thread(target=self.server.shutdown,daemon=True).start(); return
            return self.send({'error':'Nicht gefunden'},404)
        except Exception as e:
            self.send({'error':str(e) or type(e).__name__},400)

def make_server(port:int=0,base:Path=BASE):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler); server.daemon_threads=True
    server.app=App(base); server.app.origin=f'http://127.0.0.1:{server.server_address[1]}'
    return server

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--no-browser',action='store_true'); parser.add_argument('--browser',action='store_true'); parser.add_argument('--port',type=int,default=0); args=parser.parse_args()
    srv=make_server(args.port); url=srv.app.origin+'/#'+srv.app.token
    # Use a local lock so two wizard instances cannot write to the same workspace.
    import socket
    gate=socket.socket()
    try:
        gate.bind(('127.0.0.1',43871)); gate.listen(1)
    except OSError:
        current=srv.app.engine.local/'connection.json'
        if current.is_file():
            existing=json.loads(current.read_text(encoding='utf-8')).get('url','')
            if re.fullmatch(r'http://127\.0\.0\.1:[0-9]+/#[A-Za-z0-9_-]+',existing):
                from desktop import open_window
                open_window(existing,srv.app.engine.base,browser_only=args.browser)
        print('Ein TCS-Assistent läuft bereits. Alten Assistenten zuerst beenden, dann STARTEN.cmd erneut öffnen.'); srv.server_close(); return 1
    session={'url':url,'pid':os.getpid(),'origin':srv.app.origin}
    jsonwrite(srv.app.engine.local/'connection.json',session)
    print('TCS Remaster Installer 0.4.0\nNur lokal; dieses Fenster während der Installation offen lassen.\n'+url,flush=True)
    if not args.no_browser:
        from desktop import open_window
        mode=open_window(url,srv.app.engine.base,browser_only=args.browser)
        print('Oberfläche: '+mode,flush=True)
    srv.app.workflow.start()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        srv.app.workflow.stop_event.set()
        srv.server_close(); gate.close()
        (srv.app.engine.local/'connection.json').unlink(missing_ok=True)
    return 0
if __name__=='__main__': raise SystemExit(main())
