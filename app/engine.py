"""Local asset staging, conflict review, reversible file installation and safe publishing."""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable
from safety import (ANCHORS, BLOCKED, MAX_BYTES, MAX_FILES, BuildError, Source, bytehash, checked_entries,
                    digest, find_7zip, linked, no_links, safe_rel, unpack_external)
from merge import merge3, decode
from recipe_overlays import choose_overlay

APP_ID='nor.per.tcs.remaster.local'
EXE='LEGOStarWarsSaga.exe'
META='.tcs-remaster'

def now(): return datetime.now(timezone.utc).isoformat()
def jsonwrite(path:Path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(value,f,indent=2,ensure_ascii=False); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)

def casepath(root:Path,rel:str) -> Path:
    p=no_links(root)
    for part in safe_rel(rel).split('/'):
        if p.is_dir():
            candidates=[x for x in p.iterdir() if x.name.casefold()==part.casefold()]
            if len(candidates)>1: raise BuildError(f'Mehrdeutige Groß-/Kleinschreibung: {p/part}')
            p=candidates[0] if candidates else p/part
        else:
            if p.exists(): raise BuildError(f'Datei blockiert einen benötigten Unterordner: {p}')
            p=p/part
        no_links(p)
    return p

def within(a:Path,b:Path):
    a=a.absolute(); b=b.absolute()
    return a==b or b in a.parents

def describe_game(path:str) -> dict:
    if not isinstance(path,str) or not path.strip(): raise BuildError('Bitte zuerst den Spielordner auswählen.')
    game=no_links(Path(path.strip().strip('"')))
    if not game.is_dir(): raise BuildError('Bitte den vorhandenen Spielordner auswählen, nicht die ZIP oder nur steamapps.')
    exe=casepath(game,EXE)
    if not exe.is_file(): raise BuildError(f'{EXE} nicht gefunden. In Steam → Verwalten → Lokale Dateien durchsuchen.')
    with exe.open('rb') as f:
        if f.read(2)!=b'MZ': raise BuildError('Die ausgewählte EXE ist keine erkennbare Windows-Programmdatei.')
    loose=[]
    for name in ('chars','stuff','levels'):
        p=casepath(game,name)
        if p.is_dir() and any(p.iterdir()): loose.append(name)
    prepared=len(loose)==3
    active=(game/META/'journal.json').is_file()
    return {'path':str(game),'exe':str(exe),'exe_sha256':digest(exe),'loose_folders':loose,
            'prepared_structure':prepared,'active_install':active,
            'preparation_backup': (game/'.tcs-preparation'/'journal.json').is_file(),
            'active_data_archives': [p.name for p in game.iterdir() if p.is_file() and re.fullmatch(r'game\d*\.dat',p.name,re.I)],
            'data_archives': [p.name for p in game.iterdir() if p.is_file() and p.suffix.lower()=='.dat'],
            'note':('Lose Daten erkannt. Ob diese EXE sie lädt, muss im vorbereiteten Modding-Setup geprüft sein.' if prepared else
                    'Original-DATs erkannt bzw. lose Spieldaten fehlen. Über „Automatisch vorbereiten“ werden Archive geprüft, isoliert entpackt und gesichert. Die EXE wird nicht gepatcht.')}

def guess_module(name:str,modules:list[dict]) -> str|None:
    if not isinstance(name,str): return None
    from matching import identify
    identified=identify(name,modules)
    if identified:return identified['id']
    text=re.sub(r'[^a-z0-9]+',' ',name.lower())
    if ('patch' in text or 'compatib' in text) and 'additional' in text: return 'infinities-al-patch'
    if ('refinement' in text or 'infinities' in text or 'better and improved' in text) and 'patch' not in text: return 'infinities'
    if 'additional' in text and 'level' in text: return 'additional-levels-mo'
    if 'modern' in text and 'overhaul' in text and 'patch' not in text: return 'modern-overhaul'
    return None

def suggest_roots(roots:list[str],mode:str) -> list[str]:
    """Only a suggestion. The UI requires confirmation of actual roots and variant."""
    if len(roots)==1: return list(roots)
    classic=[r for r in roots if 'classic' in r.lower()]
    deny=('optional','film accurate','e3 2019','vader','modern icon','mo icon')
    common=[r for r in roots if not any(w in r.lower().replace('_',' ').replace('-',' ') for w in deny)
            and not any(w in r.lower() for w in ('classic','icon'))]
    # Prefer shallow common roots; do not include every nested alternative.
    if common:
        shallow=min(len(r.split('/')) if r else 0 for r in common)
        common=[r for r in common if (len(r.split('/')) if r else 0)==shallow]
    if mode=='classic': return common+classic[:1]
    return common[:1] if len(common)==1 else []

class Engine:
    def __init__(self,base:Path):
        self.base=base.absolute(); self.profile=json.loads((base/'profile.json').read_text(encoding='utf-8'))
        self.local=no_links(base/'.local'); self.local.mkdir(exist_ok=True)
        for n in ('imports','unpacked','objects','plans','builds','exports'):
            no_links(self.local/n).mkdir(exist_ok=True)
        self.statefile=self.local/'session.json'
        self.state=json.loads(self.statefile.read_text(encoding='utf-8')) if self.statefile.exists() else {'sources':[],'selections':{},'options':{}}
        if not isinstance(self.state,dict): raise BuildError('Die lokale Sitzung ist ungültig. .local/session.json separat sichern und Diagnose prüfen.')
        for key in ('selections','options','decisions','automation'):
            if not isinstance(self.state.get(key),dict): self.state[key]={}
        if not isinstance(self.state.get('sources'),list): self.state['sources']=[]
        for key in ('game','baseline'):
            if not isinstance(self.state.get(key),str): self.state[key]=''
        self.plan=None; self.lock=threading.RLock()
    def save(self): jsonwrite(self.statefile,self.state)
    def import_source(self,path:str,display_name:str|None=None,log:Callable=print) -> dict:
        p=no_links(Path(path)); name=display_name or p.name
        if not p.exists(): raise BuildError('Die ausgewählte Datei ist nicht mehr vorhanden.')
        if p.is_file():
            from diagnostics import check_cancel
            check_cancel(log)
            archive_hash=digest(p)
            for old in self.state['sources']:
                if old.get('archive_sha256')==archive_hash and Path(old.get('path','')).exists():
                    log('Dieses unveränderte Archiv wurde bereits importiert: '+old['name'])
                    return old
        if p.is_file() and p.suffix.lower() in ('.7z','.rar'):
            log('Archiv wird isoliert mit 7-Zip geprüft und entpackt: '+name)
            source_path=unpack_external(p,self.local/'unpacked',log=log)
        else: source_path=p
        with Source(source_path) as src:
            roots=src.roots()
            if not roots: raise BuildError('Keine CHARS/STUFF/LEVELS-Daten erkannt. Eventuell falsches Archiv oder ZIP in ZIP. Das enthaltene Modarchiv separat hinzufügen.')
            counts={r:len(src.selected(r)) for r in roots}
            count=len(src.entries)
        item={'id':uuid.uuid4().hex,'name':name,'path':str(source_path),'archive_path':str(p),
              'archive_sha256':digest(p) if p.is_file() else None,'roots':roots,'root_counts':counts,
              'file_count':count,'guessed_module':guess_module(name,self.profile['modules']),
              'authenticity_verified':False}
        self.state['sources'].append(item)
        guessed=item['guessed_module']
        if guessed and not self.state['selections'].get(guessed,{}).get('source_id'):
            mod=next(m for m in self.profile['modules'] if m['id']==guessed)
            self.state['selections'][guessed]={'source_id':item['id'],'roots':suggest_roots(roots,mod['root_mode']),'confirmed':False,'enabled':self.state['selections'].get(guessed,{}).get('enabled',mod.get('default_enabled',True))}
        self.save(); self.plan=None
        return item
    def get_source(self,sid:str):
        for s in self.state['sources']:
            if s['id']==sid: return s
        raise BuildError('Quelle nicht gefunden. Bitte Archiv erneut hinzufügen.')
    def put_blob(self,source:Source,entry) -> dict:
        fd,p=tempfile.mkstemp(dir=self.local/'objects',prefix='tmp-'); os.close(fd); temp=Path(p)
        try:
            h=source.copy(entry,temp); final=self.local/'objects'/h
            if not final.exists(): os.replace(temp,final)
            return {'sha256':h,'bytes':entry.size}
        finally: temp.unlink(missing_ok=True)
    def blob(self,sha:str) -> Path:
        if not re.fullmatch(r'[a-f0-9]{64}',sha): raise BuildError('Ungültige Objekt-ID.')
        return no_links(self.local/'objects'/sha)
    def put_bytes(self,data:bytes) -> dict:
        h=bytehash(data); p=self.blob(h)
        if not p.exists(): p.write_bytes(data)
        return {'sha256':h,'bytes':len(data)}
    def make_plan(self,settings:dict,log:Callable=print) -> dict:
        from diagnostics import phase, check_cancel, progress
        from steps import stage
        stage(log,'compare','running','Dateiplan erstellen und Konflikte prüfen')
        phase(log, 'compare', 'Modauswahl und Dateikonflikte prüfen …')
        check_cancel(log)
        game=describe_game(settings.get('game',''))
        target=Path(game['path'])
        if within(self.base,target) or within(target,self.base): raise BuildError('Installer und Spielordner dürfen nicht ineinander liegen. ZIP separat entpacken.')
        selections=settings.get('selections',self.state['selections']); options=settings.get('options',{})
        selected=[m for m in self.profile['modules'] if selections.get(m['id'],{}).get('enabled',False)]
        if not selected: raise BuildError('Mindestens einen Mod auswählen.')
        ids={m['id'] for m in selected}
        if 'additional-levels-mo' in ids and 'infinities' in ids and 'infinities-al-patch' not in ids:
            raise BuildError('Additional Levels + Infinities brauchen in diesem Profil den passenden Additional-Levels-Patch.')
        if 'ep3-additions' in ids and 'infinities' in ids and 'infinities-vader-patch' not in ids:
            raise BuildError('Kapitel-6-Addon + Infinities benötigen hier den Vader-Enhancer-Patch.')
        for m in selected:
            if not set(m['requires'])<=ids: raise BuildError('Fehlende Abhängigkeit für '+m['name'])
            sel=selections[m['id']]
            if not sel.get('confirmed') or not sel.get('roots'): raise BuildError('Datei und Daten-Unterordner bestätigen: '+m['name'])
        stage(log,'mapping','done','Aktivierte Module, Unterordner und Abhängigkeiten bestätigt')
        baseline=None
        if options.get('baseline_confirmed'):
            bp=settings.get('baseline') or game['path']
            baseline=no_links(Path(bp))
            if not baseline.is_dir(): raise BuildError('Unveränderte Referenzkopie fehlt.')
            if (baseline/META/'journal.json').exists(): raise BuildError('Aktiv modifizierte Installation ist keine unveränderte Referenz. Zuerst wiederherstellen oder andere Referenz wählen.')
        versions={}; display={}; total=0; files=0; sources_used=[]
        for m in selected:
            sel=selections[m['id']]; item=self.get_source(sel['source_id'])
            if within(Path(item['path']),target): raise BuildError('Ein Mod-Quellordner darf nicht innerhalb des Spielordners liegen.')
            archive_path=Path(item['archive_path'])
            if item.get('archive_sha256') and (not archive_path.is_file() or digest(no_links(archive_path))!=item['archive_sha256']):
                raise BuildError('Archiv seit dem Import verändert. Erneut hinzufügen: '+item['name'])
            check_cancel(log)
            log('Prüfe und hashe '+m['name'])
            with Source(item['path']) as src:
                for root in sel['roots']:
                    for rel,e in src.selected(root):
                        total+=e.size; files+=1
                        if total>MAX_BYTES or files>MAX_FILES: raise BuildError('Gesamtprofil größer als 24 GiB / 160.000 Dateien.')
                        if shutil.disk_usage(self.local).free<e.size+256*1024**2: raise BuildError('Zu wenig freier Speicher für den Build.')
                        key=rel.casefold(); display.setdefault(key,rel)
                        entry={**self.put_blob(src,e),'module':m['id'],'root':root}
                        versions.setdefault(key,[]).append(entry)
            sources_used.append({'module':m['id'],'archive':item['name'],'sha256':item['archive_sha256'],'roots':sel['roots'],'authenticity_verified':False})
        checked_entries(list(display.values()))
        decisions=settings.get('decisions',{}); records=[]; conflicts=[]
        for index,(key,raw) in enumerate(versions.items()):
            if index%300==0:
                check_cancel(log)
                log(f'Dateivergleich {index+1}/{len(versions)}')
                progress(log,index+1,len(versions))
            path=display[key]; current=casepath(target,path)
            if current.exists() and not current.is_file(): raise BuildError('Ziel ist ein Verzeichnis statt einer Datei: '+path)
            before=digest(current) if current.is_file() else None
            unique=[]
            for v in raw:
                if not unique or unique[-1]['sha256']!=v['sha256']: unique.append(v)
            hashes={v['sha256'] for v in unique}
            row={'path':path,'key':key,'versions':unique,'target_sha256':before,'target_exists':before is not None,
                 'target_rel':current.relative_to(target).as_posix(),'status':'ready','strategy':'new-or-replacement','reason':''}
            winner=unique[-1]
            if len(hashes)==1: row['strategy']='identical-deduplicated' if len(raw)>1 else 'single-mod'
            else:
                decision=decisions.get(key)
                overlay=choose_overlay(path,unique)
                proposal=None
                basepath=casepath(baseline,path) if baseline else None
                if not overlay and basepath and basepath.is_file() and basepath.stat().st_size<=2*1024**2:
                    base=basepath.read_bytes(); merged=base; success=True
                    for v in unique:
                        if v['bytes']>2*1024**2: success=False; break
                        result=merge3(base,merged,self.blob(v['sha256']).read_bytes(),path)
                        if not result.ok: success=False; row['reason']=result.reason; break
                        merged=result.data
                    if success:
                        proposal={**self.put_bytes(merged),'module':'three-way-merge','root':''}
                        row['merge_proposal']=proposal
                if decision and decision.get('type')=='provider':
                    candidates=[v for v in unique if v['module']==decision.get('module')]
                    if not candidates: raise BuildError('Konfliktentscheidung passt nicht mehr zu '+path)
                    winner=candidates[-1]; row['strategy']='explicit-variant-replacement'; row['reason']='Bewusst gewählte vollständige Variante; keine Zusammenführung.'
                elif decision and decision.get('type')=='patch':
                    pp=no_links(Path(decision.get('path','')))
                    if not pp.is_file() or pp.suffix.lower() in BLOCKED: raise BuildError('Manuelle Patchdatei fehlt oder ist ausführbar.')
                    if pp.stat().st_size>512*1024**2: raise BuildError('Manuelle Patchdatei zu groß.')
                    winner={**self.put_bytes(pp.read_bytes()),'module':'user-merged-file','root':''}
                    row['strategy']='explicit-patch-file'; row['reason']='Vom Nutzer gewählte Ersatz-/Merge-Datei; keine automatisierte Spielprüfung.'
                elif overlay:
                    winner=unique[overlay[0]]; row['strategy']='recipe-overlay'; row['reason']=overlay[1]
                elif proposal:
                    winner=proposal; row['strategy']='automatic-three-way-text'; row['reason']='Nicht überlappende Textänderungen gegen bestätigte unveränderte Referenz automatisch vereint; Spiellogik ungeprüft.'
                else:
                    row['status']='blocked'; row['strategy']='needs-review'
                    row['reason']=row['reason'] or 'Unbekannte Dateikombination. Automatik stoppt; passende Version oder geprüften Kompatibilitätspatch verwenden.'
                    conflicts.append(row)
            row['result']=winner; records.append(row)
        if options.get('graphics'):
            for local,rel in [('graphics/TCS_ClassicPlus.ini','TCS_ClassicPlus.ini'),('graphics/Shaders/TCS_ClassicPlus.fx','reshade-shaders/Shaders/TCS_ClassicPlus.fx')]:
                p=casepath(target,rel); data=(self.base/local).read_bytes()
                records.append({'path':rel,'key':rel.casefold(),'target_rel':p.relative_to(target).as_posix(),'target_sha256':digest(p) if p.is_file() else None,
                                'target_exists':p.is_file(),'versions':[],'result':{**self.put_bytes(data),'module':'own-graphics'},'status':'ready','strategy':'own-optional-preset','reason':'ReShade-Runtime und Presetauswahl bleiben separat.'})
        checked_entries([r['path'] for r in records])
        plan={'id':uuid.uuid4().hex,'created':now(),'game':game,'baseline':str(baseline) if baseline else None,
              'sources':sources_used,'records':records,'conflicts':conflicts,'settings':settings,
              'counts':{'files':len(records),'conflicts':len(conflicts),'bytes':sum(r['result']['bytes'] for r in records),
                        'recipe_overlays':sum(r['strategy']=='recipe-overlay' for r in records),
                        'text_merges':sum(r['strategy']=='automatic-three-way-text' for r in records),
                        'text_proposals':sum(bool(r.get('merge_proposal')) for r in records)},
              'gameplay_tested':False,'author_archive_hashes_verified':False}
        jsonwrite(self.local/'plans'/(plan['id']+'.json'),plan)
        self.plan=plan; self.state.update({'selections':selections,'options':options,'game':game['path'],'baseline':settings.get('baseline',''),'decisions':decisions})
        self.save()
        stage(log,'compare','waiting' if conflicts else 'done',str(len(conflicts))+' offene Konflikte' if conflicts else 'Dateiplan ohne offene Konflikte')
        return plan
    def materialize(self,plan:dict,destination:Path,log:Callable=print) -> None:
        if plan['counts']['conflicts']: raise BuildError('Es gibt ungelöste Konflikte. Keine Dateien werden installiert.')
        if destination.exists() and any(destination.iterdir()): raise BuildError('Build-Ziel muss neu und leer sein.')
        destination.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(destination).free<plan['counts']['bytes']+256*1024**2: raise BuildError('Zu wenig Speicher für den Build.')
        for i,row in enumerate(plan['records']):
            if i%300==0: log(f'Baue {i+1}/{len(plan["records"])} Dateien')
            source=self.blob(row['result']['sha256'])
            if digest(source)!=row['result']['sha256']: raise BuildError('Gehashtes Objekt wurde nach dem Vergleich verändert.')
            p=destination.joinpath(*safe_rel(row['path']).split('/')); p.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,p)
    def make_build(self,plan:dict,log:Callable=print) -> dict:
        build=self.local/'builds'/plan['id']; assets=build/'TCS-Remaster-Local'/'Redirector'
        if build.exists(): raise BuildError('Dieser Plan wurde schon gebaut. Neu prüfen, um einen neuen Build anzulegen.')
        try:
            self.materialize(plan,assets,log)
            config={'ModId':APP_ID,'ModName':'TCS Remaster Classic Plus (local, untested)','ModAuthor':'Local recipe; original authors credited',
                    'ModVersion':'0.4.0','ModDescription':'User-supplied assets; not a standalone game. Prepared TCS and Reloaded File Redirector required.',
                    'ModDependencies':['reloaded.universal.redirector'],'OptionalDependencies':[],'SupportedAppId':['legostarwarssaga']}
            jsonwrite(build/'TCS-Remaster-Local'/'ModConfig.json',config)
            # Own ReShade files live OUTSIDE Redirector. The injector resolves these from the game folder.
            gfx=build/'graphics-for-game-folder'
            for rel in ('TCS_ClassicPlus.ini','reshade-shaders/Shaders/TCS_ClassicPlus.fx'):
                p=assets/rel
                if p.exists():
                    dest=gfx/rel; dest.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(p),dest)
            jsonwrite(build/'build-report.json',plan)
            (build/'NUR_PRIVAT_NICHT_HOCHLADEN.txt').write_text('Dieser lokale Build enthält fremde Moddateien. Nicht als öffentliches Modpack hochladen. Für GitHub ausschließlich den Installer-Export benutzen.\n',encoding='utf-8')
            archive=build/'TCS-Remaster-Local.zip'
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
                for p in sorted((build/'TCS-Remaster-Local').rglob('*')):
                    if p.is_file(): z.write(p,p.relative_to(build/'TCS-Remaster-Local').as_posix())
            result={'folder':str(build),'archive':str(archive),'status':'BUILT_NOT_GAME_TESTED'}
            self.state['last_build']=result; self.save(); return result
        except Exception:
            shutil.rmtree(build,ignore_errors=True); raise
    @staticmethod
    def _running():
        from processes import game_running
        return game_running(EXE)
    def install(self,plan:dict,log:Callable=print,fail_after:int|None=None) -> dict:
        from diagnostics import phase, check_cancel, progress
        phase(log, 'install', 'Geprüfte Moddateien sichern und installieren …')
        check_cancel(log)
        settings=plan['settings']; opts=settings.get('options',{})
        if not opts.get('prepared_confirmed') or not opts.get('clean_target_confirmed'):
            raise BuildError('Vorbereitete, unveränderte Spielkopie und funktionierendes Laden loser Mods bestätigen. Nicht blind in eine beliebige Steam-Installation kopieren.')
        if plan['counts']['conflicts']: raise BuildError('Ungelöste Konflikte blockieren die Installation.')
        game=no_links(Path(plan['game']['path'])); desc=describe_game(str(game))
        if desc['exe_sha256']!=plan['game']['exe_sha256']: raise BuildError('Spiel-EXE seit dem Vergleich verändert. Erneut prüfen.')
        if not desc['prepared_structure'] or desc.get('active_data_archives'): raise BuildError('Originalarchive sind noch aktiv oder lose Daten fehlen. Zuerst „Automatisch vorbereiten“ ausführen.')
        if desc['active_install']: raise BuildError('Installation/unterbrochene Transaktion bereits vorhanden. Erst über „Wiederherstellen“ zurücksetzen.')
        if self._running(): raise BuildError('TCS läuft noch. Spiel vollständig schließen.')
        meta=no_links(game/META)
        if meta.exists(): raise BuildError('Ein Sicherungsordner existiert bereits. Bitte den früheren Zustand zuerst prüfen/wiederherstellen.')
        # Compare every target against the exact preflight snapshot before creating backups.
        for row in plan['records']:
            p=casepath(game,row['target_rel'])
            current=digest(p) if p.is_file() else None
            if current!=row['target_sha256']: raise BuildError('Spielordner seit der Prüfung verändert: '+row['path']+'. Neu prüfen.')
        if shutil.disk_usage(game).free<2*plan['counts']['bytes']+sum(casepath(game,r['target_rel']).stat().st_size for r in plan['records'] if r['target_exists'])+256*1024**2:
            raise BuildError('Zu wenig Speicher für Staging und vollständige Dateisicherungen.')
        journal={'schema':1,'id':plan['id'],'created':now(),'game':str(game),'status':'PREPARING','entries':[],'created_dirs':[],
                 'exe_sha256':plan['game']['exe_sha256'],
                 'modules':[m['id'] for m in self.profile['modules'] if settings.get('selections',{}).get(m['id'],{}).get('enabled')]}
        try:
            meta.mkdir(); (meta/'backup').mkdir(); (meta/'pending').mkdir()
            # PREPARING is durable before staging; no game writes happen in this state.
            jsonwrite(meta/'journal.json',journal)
            for i,row in enumerate(plan['records']):
                rel=row['target_rel']; target=casepath(game,rel)
                if row['target_exists']:
                    backup=meta/'backup'/rel; backup.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(target,backup)
                    if digest(backup)!=row['target_sha256']: raise BuildError('Sicherung fehlgeschlagen: '+rel)
                pending=meta/'pending'/rel; pending.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(self.blob(row['result']['sha256']),pending)
                if digest(pending)!=row['result']['sha256']: raise BuildError('Staging-Prüfsumme falsch.')
                journal['entries'].append({'path':rel,'before':row['target_sha256'],'after':row['result']['sha256'],'applied':False})
            # Persist a complete write-ahead snapshot once, not O(N^2) full-journal rewrites.
            missing_dirs=set()
            for entry in journal['entries']:
                parent=casepath(game,entry['path']).parent
                while not parent.exists():
                    missing_dirs.add(parent.relative_to(game).as_posix()); parent=parent.parent
            journal['created_dirs']=sorted(missing_dirs,key=lambda s:(len(s.split('/')),s))
            journal['status']='INSTALLING'; jsonwrite(meta/'journal.json',journal)
            for i,entry in enumerate(journal['entries']):
                rel=entry['path']; target=casepath(game,rel)
                if (digest(target) if target.is_file() else None)!=entry['before']: raise BuildError('Datei wurde während der Installation extern verändert: '+rel)
                parents=[]; parent=target.parent
                while not parent.exists(): parents.append(parent); parent=parent.parent
                for parent in reversed(parents):
                    parent.mkdir()
                # Every before/after hash and backup is already durable. Per-file rename is atomic.
                os.replace(meta/'pending'/rel,target)
                entry['applied']=True
                if i%300==0:
                    log(f'Installiere {i+1}/{len(journal["entries"])} Dateien')
                    progress(log,i+1,len(journal['entries']))
                if fail_after is not None and i>=fail_after: raise OSError('Synthetic injected write failure')
            journal['status']='INSTALLED'; jsonwrite(meta/'journal.json',journal)
            self.state['installed_game']=str(game); self.save()
            return {'folder':str(game),'status':'INSTALLED_NOT_GAME_TESTED','backup':str(meta/'backup')}
        except Exception:
            if (meta/'journal.json').exists():
                try: self.restore(str(game),log)
                except Exception as recovery_error:
                    log('Automatische Wiederherstellung nicht vollständig: '+str(recovery_error)+'. Backups bleiben erhalten.')
            elif meta.exists(): shutil.rmtree(meta,ignore_errors=True)
            raise
    def restore(self,game_path:str,log:Callable=print) -> dict:
        game=no_links(Path(game_path)); meta=no_links(game/META); jf=meta/'journal.json'
        if not jf.is_file(): raise BuildError('Keine Sicherung dieses Installers gefunden.')
        if self._running(): raise BuildError('TCS vor der Wiederherstellung schließen.')
        journal=json.loads(jf.read_text(encoding='utf-8'))
        if journal.get('schema')!=1 or Path(journal.get('game','')).absolute()!=game: raise BuildError('Sicherungsjournal passt nicht zum Spielordner.')
        # All targets/backups are validated before touching any file.
        for e in journal['entries']:
            p=casepath(game,e['path']); value=digest(p) if p.is_file() else None
            if value not in (e['before'],e['after']):
                raise BuildError('Später veränderte Datei wird nicht überschrieben: '+e['path']+'. Datei separat sichern/prüfen; Backup bleibt erhalten.')
            if e['before']:
                b=no_links(meta/'backup'/safe_rel(e['path']))
                if not b.is_file() or digest(b)!=e['before']: raise BuildError('Backup fehlt oder ist verändert: '+e['path'])
        journal['status']='RESTORING'; jsonwrite(jf,journal)
        for e in reversed(journal['entries']):
            p=casepath(game,e['path'])
            if e['before']:
                # Use a generated filename, never an uncontrolled game-file suffix.
                fd,tmp=tempfile.mkstemp(dir=meta,prefix='restore-'); os.close(fd)
                try:
                    shutil.copyfile(meta/'backup'/e['path'],tmp); os.replace(tmp,p)
                finally: Path(tmp).unlink(missing_ok=True)
            elif p.exists(): p.unlink()
        for rel in reversed(journal.get('created_dirs',[])):
            p=casepath(game,rel)
            try: p.rmdir()
            except OSError: pass
        shutil.rmtree(meta)
        self.state.pop('installed_game',None); self.save(); log('Gesicherte Dateien wiederhergestellt; neu installierte Dateien entfernt.')
        return {'status':'RESTORED','folder':str(game)}
    def export_installer(self) -> Path:
        allow=json.loads((self.base/'publish-allowlist.json').read_text(encoding='utf-8'))['files']
        checked_entries(allow)
        out=self.local/'exports'/('TCS_Remaster_Installer_0.4.0_Public_'+uuid.uuid4().hex[:8]+'.zip')
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for rel in allow:
                rel=safe_rel(rel)
                if rel.startswith(('.local/','.runtime/','inbox/','downloads/')) or Path(rel).suffix.lower() in {'.exe','.dll','.gsc','.dds','.zip','.7z','.rar'}:
                    raise BuildError('Private/ausführbare Datei in der Veröffentlichungs-Positivliste: '+rel)
                p=no_links(self.base/rel)
                if not p.is_file(): raise BuildError('Datei für Veröffentlichung fehlt: '+rel)
                z.write(p,'TCS_Remaster_Installer_0.4.0/'+rel)
        return out
