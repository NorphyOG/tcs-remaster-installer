"""Coordinates local preparation, authorised downloads, import and reversible install.
Automatic mode is opt-in. Ambiguous filenames/roots or unresolved conflicts always
pause the workflow. Data-level success is not presented as a gameplay test.
"""
from __future__ import annotations
import json
import os
import re
import threading
import time
from collections import deque
from pathlib import Path
from engine import describe_game, jsonwrite, digest
from safety import BuildError, find_7zip
from nettools import Tools, require_windows
from diagnostics import phase, progress, check_cancel
from steps import stage
from matching import identify, assess
from preparation import stage_preparation, commit_preparation, restore_preparation, check_writable
from nexus import Nexus, DownloadWatch, parse_nxm, norm
from windows import elevated_action, protocol_status, create_shortcuts


def default_download_folder() -> str:
    """Use the user's Windows Downloads Known Folder, not a hard-coded username."""
    from safety import no_links
    candidates=[]
    if os.name=='nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                val=winreg.QueryValueEx(key,'{374DE290-123F-4565-9164-39C4925E467B}')[0]
                if isinstance(val,str):candidates.append(Path(os.path.expandvars(val)))
        except OSError:pass
    candidates.append(Path.home()/'Downloads')
    for p in candidates:
        try:
            if no_links(p).is_dir(): return str(p)
        except (OSError,BuildError):continue
    return ''


def automatic_roots(roots: list[str], mode: str) -> list[str]:
    from matching import roots_for_recipe
    return roots_for_recipe(roots,mode)


class Workflow:
    def __init__(self, app):
        self.app=app; self.engine=app.engine; self.tools=Tools(self.engine.local)
        self.tools.load_sevenzip()
        self.nexus=Nexus(self.engine.profile,self.engine.local)
        self.watch=DownloadWatch(self.engine.profile); self.nxm_queue=deque(maxlen=10)
        self.lock=threading.RLock(); self.stop_event=threading.Event()
        self.message='Automatik ist noch nicht gestartet.'
        self.last_import=None;self.watch_paused=False
        (self.engine.base/'mods').mkdir(exist_ok=True)
        state=self.engine.state
        defaults={'allow_tools':False,'auto_mapping':False,'watch_enabled':False,'watch_folder':'','armed':False,
                  'desktop_shortcut':True,'auto_watch':True,'auto_nexus':True,'watch_local_mods':True}
        for key,val in defaults.items():state['automation'].setdefault(key,val)
        if not state['automation'].get('watch_folder'):state['automation']['watch_folder']=default_download_folder()
        # Avoid importing the same watched archive again after a restart.
        for item in state['sources']:
            try:
                p=Path(item['archive_path'])
                if p.is_file():
                    st=p.stat();self.watch.done[str(p)]=(st.st_size,st.st_mtime_ns)
            except (OSError,KeyError,TypeError):pass
        # Never resume write permission automatically after process restart.
        state['automation']['armed']=False
        for m in self.engine.profile['modules']:
            state['selections'].setdefault(m['id'],{'source_id':'','roots':[],'enabled':m.get('default_enabled',True),'confirmed':False})
    def public(self):
        with self.lock:
            return {'nexus':self.nexus.status(),'automation':dict(self.engine.state['automation']),
                    'message':self.message,'watch_paused':self.watch_paused,'missing':self.missing(),'queued_nxm':len(self.nxm_queue),'last_import':self.last_import,
                    'nxm_protocol':protocol_status(),'watch_folders':self.watch_folders(),
                    'inventory':self.inventory(),'readiness':self.engine.state.get('readiness')}
    def configure(self, data):
        a=self.engine.state['automation']
        for key in ('allow_tools','auto_mapping','watch_enabled','desktop_shortcut','auto_watch','auto_nexus','watch_local_mods'):
            if key in data:a[key]=data[key] is True
        if 'watch_folder' in data:
            if not isinstance(data['watch_folder'],str) or not data['watch_folder'].strip():raise BuildError('Bitte einen gültigen Downloadordner auswählen.')
            path=Path(data['watch_folder']).expanduser().absolute()
            from safety import no_links
            if not no_links(path).is_dir(): raise BuildError('Downloadordner nicht gefunden.')
            a['watch_folder']=str(path)
        if data.get('watch_enabled') is True:
            self.watch_paused=False;self.watch.retry_failed()
        self.engine.save();return self.public()
    def tool_consent(self):
        if not self.engine.state['automation'].get('allow_tools'):
            raise BuildError('Werkzeugdownload zuerst ausdrücklich freigeben. Es werden nur die angegebenen offiziellen Werkzeuge eingerichtet.')
    def import_data(self, path, display_name=None, log=print, module_id=None, nexus_metadata=None):
        phase(log,'import_mod','Modarchiv erkennen und zuordnen …')
        check_cancel(log)
        if not isinstance(path,str) or not path:raise BuildError('Ein Modarchiv wurde noch nicht ausgewählt.')
        if Path(path).suffix.lower() in ('.7z','.rar') and not find_7zip():
            self.tool_consent();self.tools.sevenzip(log)
        item=self.engine.import_source(path,display_name,log)
        detected=identify(item['name'],self.engine.profile['modules'])
        if detected and module_id and module_id!=detected['id']:
            log('Downloadkarte korrigiert: '+detected['name']+' statt der gewählten anderen Mod. Keine falsche Patchzuordnung.')
        module_id=detected['id'] if detected else module_id or item.get('guessed_module')
        module=next((m for m in self.engine.profile['modules'] if m['id']==module_id),None)
        if module:
            choice=self.engine.state['selections'].setdefault(module_id,{})
            if choice.get('source_id')==item['id'] and choice.get('confirmed'):
                log('Bestätigte Zuordnung wird beibehalten: '+module['name'])
                return item
            # Never silently replace a different confirmed archive when two versions
            # or alternative uploads coexist in the watched folder.
            previous=next((s for s in self.engine.state['sources'] if s['id']==choice.get('source_id')),None)
            competing=bool(previous and previous['id']!=item['id'] and choice.get('confirmed'))
            selected_roots=automatic_roots(item['roots'],module['root_mode'])
            assessment=assess(item['name'],module,nexus_metadata)
            item['version_check']=assessment
            if not assessment['matches'] or competing:selected_roots=[]
            item['review_reason']=('Zweite abweichende Archivfassung vorhanden. Version bewusst auswählen; keine automatische Ersetzung.' if competing else assessment['reason']) or ('' if selected_roots else 'Unterordner/Classic-Variante nicht eindeutig. Einmal in Schritt 3 prüfen.')
            permitted=self.engine.state['automation'].get('auto_mapping') and bool(selected_roots)
            choice.update({'source_id':item['id'],'roots':selected_roots,
                           'confirmed':bool(permitted),'enabled':choice.get('enabled',module.get('default_enabled',True))})
            item['mapping_method']='nexus_metadata_and_structure' if nexus_metadata else 'filename_and_structure_not_authenticity'
            item['auto_mapping_accepted']=bool(permitted)
            if nexus_metadata:item['nexus']={k:v for k,v in nexus_metadata.items() if k in ('module','mod_id','file_id','name','file_name','version')}
            if not permitted:self.message='Archiv übernommen. Variante/Unterordner in Schritt 3 einmal prüfen: '+module['name']
        self.last_import={'name':item['name'],'module':module_id,'confirmed':bool(module and choice.get('confirmed')),'event_id':time.time_ns()}
        self.engine.plan=None
        self.engine.state.pop('readiness',None)
        self.engine.save();self.refresh_inventory(log);return item
    def prepare(self, game, log=print):
        require_windows()
        stage(log,'prepare','running','Spielkopie prüfen und Originaldaten vorbereiten')
        phase(log,'inspect','Spielordner und Ausgangszustand prüfen …')
        check_cancel(log)
        info=describe_game(game)
        self.engine.state['game']=info['path']
        if info['active_install']:raise BuildError('Ein Modbuild ist bereits installiert. Vor einem erneuten Einbau zuerst die Modinstallation wiederherstellen; keine Dateien werden doppelt installiert.')
        if info['prepared_structure'] and not info['active_data_archives']:
            self.engine.state['options']['prepared_confirmed']=True;self.engine.save()
            stage(log,'prepare','done','Lose Spieldaten vorhanden; erneutes Entpacken nicht nötig')
            return {'prepared':True,'status':'STRUCTURE_PRESENT_NOT_GAME_TESTED','game':info['path']}
        self.engine.state['options']['prepared_confirmed']=False;self.engine.save()
        self.tool_consent()
        manifest=stage_preparation(game,self.engine.local,log,tools=self.tools)
        check_cancel(log)
        if check_writable(Path(info['path'])):
            result=commit_preparation(manifest,self.engine.local,log)
        else:
            log('Windows fragt jetzt nach der Freigabe für das Schreiben in den Spielordner. Downloader bleibt ohne Administratorrechte.')
            result=elevated_action(self.engine.base,'prepare_commit',{'manifest':str(manifest)})
        self.engine.state['game']=info['path'];self.engine.state['options']['prepared_confirmed']=True
        self.engine.plan=None;self.engine.save();self.message='Lose Spieldaten vorbereitet. Originalarchive sind gesichert; Spieltest steht aus.'
        stage(log,'prepare','done','Spieldaten vorbereitet, Originalarchive gesichert')
        return result
    def install(self, plan, log=print):
        require_windows();check_cancel(log);game=Path(plan['game']['path'])
        stage(log,'install','running','Originaldateien sichern und Mods installieren')
        if check_writable(game):result=self.engine.install(plan,log)
        else:
            planfile=self.engine.local/'plans'/(plan['id']+'.json')
            log('Windows-Schreibfreigabe für den geprüften Dateiplan anfordern …')
            result=elevated_action(self.engine.base,'install',{'plan_id':plan['id'],'sha256':digest(planfile)})
            self.engine.state['installed_game']=str(game);self.engine.save()
        self.engine.state['automation']['armed']=False
        self.engine.save()
        if self.engine.state['automation'].get('desktop_shortcut'):
            try:
                create_shortcuts(self.engine.base,str(game));log('Desktop-Verknüpfung für Spiel und Modpack-Verwaltung erstellt.')
            except BuildError:
                log('Dateien installiert; Desktop-Verknüpfung nicht erstellt (eventuell schon vorhanden). Sie lässt sich separat anlegen.')
        stage(log,'install','done','Moddateien installiert; Sicherung vorhanden')
        result['readiness']=self.verify(log)
        self.message='Dateien installiert und geprüft. Jetzt den ausgewählten Spielbuild starten; Spieltest bleibt separat.'
        return result
    def restore(self, game, original=False, log=print):
        require_windows()
        self.engine.state['automation']['armed']=False;self.engine.save()
        if not check_writable(Path(game)):
            result=elevated_action(self.engine.base,'prepare_restore' if original else 'restore',{'game':game})
        else:result=restore_preparation(game,log) if original else self.engine.restore(game,log)
        if not original:self.engine.state.pop('installed_game',None)
        else:self.engine.state['options']['prepared_confirmed']=False
        self.engine.plan=None;self.engine.state.pop('readiness',None);self.engine.save()
        self.app.steps.reset()
        return result
    def missing(self):
        missing=[]
        for m in self.engine.profile['modules']:
            s=self.engine.state['selections'].get(m['id'],{})
            if s.get('enabled') and not (s.get('source_id') and s.get('confirmed') and s.get('roots')):missing.append(m['name'])
        return missing
    def arm(self, confirmation, log=print):
        require_windows()
        if confirmation!='PREPARE_AND_INSTALL':raise BuildError('Automatische Vorbereitung und Installation ausdrücklich bestätigen.')
        a=self.engine.state['automation']
        if not self.engine.state['options'].get('clean_target_confirmed'):
            raise BuildError('Zuerst bestätigen, dass die gewählte Steam-Kopie keine unbekannten alten Mods enthält.')
        self.tool_consent();check_cancel(log)
        self.watch_paused=False;self.watch.retry_failed()
        if a.get('auto_watch'):
            folder=a.get('watch_folder') or default_download_folder()
            if folder:
                a['watch_folder']=folder;a['watch_enabled']=True
                log('Automatische Übernahme ist aktiv: Nur passende fertige Modarchive im gewählten Downloadordner werden gelesen.')
            else:log('Kein Downloadordner erkannt. Archive können über die Downloadkarten hinzugefügt werden.')
        a['armed']=True;self.engine.save()
        try:
            self.prepare(self.engine.state.get('game',''),log)
            check_cancel(log)
            if a.get('auto_nexus') and self.nexus.status()['premium'] and self.missing():
                phase(log,'download_mods','Aktivierte Rezeptdateien über Nexus laden …')
                return self.fetch_selected(log)
            return self.maybe_install(log)
        except Exception:
            a['armed']=False;self.engine.save()
            self.message='Automatik nach Fehler pausiert. Spielvorbereitung bzw. Protokoll prüfen und bewusst neu starten.'
            raise
    def on_failure(self,message,action='operation'):
        self.engine.state['automation']['armed']=False
        self.watch_paused=action not in ('import','watch-import')
        self.message=message+(' Andere passende Downloads werden weiterhin übernommen; die defekte Datei wird nicht erneut versucht.' if not self.watch_paused else '')
        self.engine.save()
    def resume(self,log=print):
        # Do not jump straight to mod installation after a failed preparation.
        # arm revalidates the target and reuses verified preparation checkpoints.
        game=self.engine.state.get('installed_game')
        if game:
            # An installed build is never installed a second time just to retry
            # a final check. Verification is read-only and cannot hide a mismatch.
            return {'readiness':self.verify(log),'installed':True}
        return self.arm('PREPARE_AND_INSTALL',log)
    def maybe_install(self, log=print):
        check_cancel(log)
        if not self.engine.state['automation']['armed']:return {'waiting':False}
        missing=self.missing()
        self.refresh_inventory(log)
        if missing:
            self.message='Vorbereitet. Warte auf Archive/Bestätigung: '+', '.join(missing)
            phase(log,'waiting_downloads',self.message)
            return {'waiting':True,'missing':missing}
        settings={k:self.engine.state.get(k,'') for k in ('game','baseline')}
        settings.update({k:self.engine.state.get(k,{}) for k in ('selections','options','decisions')})
        settings['options']=dict(settings['options'])
        settings['decisions']={}
        # Baseline trust remains explicit; valid non-overlapping text changes merge automatically.
        stage(log,'compare','running','Aktiviertes Rezept und Dateikonflikte prüfen')
        plan=self.engine.make_plan(settings,log)
        if plan['counts']['conflicts']:
            self.engine.state['automation']['armed']=False;self.engine.save()
            stage(log,'compare','waiting',str(plan['counts']['conflicts'])+' Konflikte benötigen Prüfung')
            self.message=f'{plan["counts"]["conflicts"]} Konflikte: Automatik pausiert. In Schritt 4 prüfen; keine Moddatei installiert.'
            return {'waiting':True,'conflicts':plan['counts']['conflicts'],'plan_id':plan['id']}
        stage(log,'compare','done','Dateiplan aufgelöst; keine offenen Konflikte')
        return self.install(plan,log)
    def fetch_one(self, module_id, log=print):
        data=self.nexus.fetch(module_id,log)
        item=self.import_data(data['path'],data['display_name'],log,module_id,data['nexus'])
        followup=self.maybe_install(log)
        return {'import':item,'workflow':followup}
    def fetch_selected(self, log=print):
        if not self.nexus.status()['premium']: raise BuildError('Sammeldownload benötigt Nexus Premium. Kostenlos: Downloadkarten + beobachteter Downloadordner.')
        if not self.nexus.catalog:self.nexus.resolve(log)
        for m in self.engine.profile['modules']:
            s=self.engine.state['selections'].get(m['id'],{})
            if not s.get('enabled') or s.get('source_id'):continue
            check_cancel(log)
            data=self.nexus.fetch(m['id'],log)
            self.import_data(data['path'],data['display_name'],log,m['id'],data['nexus'])
        return self.maybe_install(log)
    def receive_nxm(self,url):
        parse_nxm(url,{m['nexus']['mod_id'] for m in self.engine.profile['modules'] if m.get('nexus')})
        with self.lock:
            if len(self.nxm_queue)>=10:raise BuildError('Downloadwarteschlange voll.')
            self.nxm_queue.append(url)
            self.message='Nexus-Link empfangen. API-Schlüssel verbinden, falls noch nicht verbunden.'
        return {'queued':True}
    def watch_folders(self):
        a=self.engine.state['automation'];folders=[]
        for value in ([a.get('watch_folder')] if a.get('watch_folder') else []) + ([str(self.engine.base/'mods')] if a.get('watch_local_mods',True) else []):
            if value and value not in folders:folders.append(value)
        return folders
    def inventory(self):
        result=[]
        for m in self.engine.profile['modules']:
            selection=self.engine.state['selections'].get(m['id'],{})
            source=next((s for s in self.engine.state['sources'] if s['id']==selection.get('source_id')),None)
            result.append({'id':m['id'],'name':m['name'],'enabled':bool(selection.get('enabled')),
                           'imported':bool(source),'ready':bool(source and selection.get('confirmed') and selection.get('roots') and all(self.engine.state['selections'].get(dep,{}).get('enabled') for dep in m.get('requires',[]))),
                           'source_name':source['name'] if source else '',
                           'review_reason':source.get('review_reason','') if source else '',
                           'version_check':source.get('version_check') if source else None})
        return result
    def refresh_inventory(self,log=print):
        active=[r for r in self.inventory() if r['enabled']]
        total=len(active);received=sum(r['imported'] for r in active);ready=sum(r['ready'] for r in active)
        stage(log,'downloads','done' if total and received==total else 'waiting',
              f'{received} / {total} benötigte Archive sicher übernommen',received,total,'Archive')
        stage(log,'mapping','done' if total and ready==total else 'waiting',
              f'{ready} / {total} Varianten und Abhängigkeiten zugeordnet',ready,total,'Module')
    def verify(self,log=print):
        from readiness import verify_installation
        game=self.engine.state.get('installed_game') or self.engine.state.get('game','')
        self.engine.state.pop('readiness',None);self.engine.save()
        result=verify_installation(game,self.engine.state,log)
        self.engine.state['readiness']=result;self.engine.save()
        return result
    def start(self):
        def pump():
            while not self.stop_event.wait(3):
                if self.app.job['running'] or self.watch_paused:continue
                try:
                    with self.lock:
                        url=self.nxm_queue.popleft() if self.nxm_queue and self.nexus.status()['connected'] else None
                    if url:
                        def receive(log,url=url):
                            data=self.nexus.receive(url,log)
                            self.import_data(data['path'],data['display_name'],log,data['nexus']['module'],data['nexus'])
                            return self.maybe_install(log)
                        self.app.start_job(receive);continue
                    a=self.engine.state['automation']
                    if not a.get('watch_enabled'):continue
                    candidates=[]
                    for folder in self.watch_folders():
                        candidates.extend(self.watch.candidates(folder))
                    # Optional files are imported and labelled, never silently enabled.
                    order={m['id']:i for i,m in enumerate(self.engine.profile['modules'])}
                    candidates.sort(key=lambda c:order.get(c['module'],999))
                    if not candidates:continue
                    candidate=candidates[0]
                    # Failed signatures are paused, not permanently counted as imported.
                    self.watch.mark_failed(candidate)
                    def import_watched(log,candidate=candidate):
                        before=Path(candidate['path']).stat()
                        if (before.st_size,before.st_mtime_ns)!=candidate['signature']:raise BuildError('Download ist noch in Änderung. Erneut hinzufügen, sobald er fertig ist.')
                        item=self.import_data(candidate['path'],log=log,module_id=candidate['module'])
                        self.watch.mark_done(candidate)
                        return {'import':item,'workflow':self.maybe_install(log)}
                    self.app.start_job(import_watched,action='watch-import')
                except BuildError as exc:
                    self.message=str(exc)
                except Exception:
                    self.message='Automatik pausiert nach unerwartetem Fehler. Manueller Import bleibt möglich.'
        threading.Thread(target=pump,daemon=True).start()
