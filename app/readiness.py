"""Verify the actual selected installation. File verification is not gameplay QA."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path
from engine import describe_game, META, casepath, digest, now
from safety import BuildError, no_links, safe_rel, checked_entries
from diagnostics import phase, progress, check_cancel
from steps import stage


def verify_installation(game, state, log=print):
    stage(log,'verify','running','Installierte Dateien und ausgewähltes Startziel prüfen')
    phase(log,'verify_install','Installationsprüfung: jede Moddatei mit ihrem SHA-256 vergleichen …')
    info=describe_game(game);root=Path(info['path']);journal_file=no_links(root/META/'journal.json')
    if not journal_file.is_file():raise BuildError('START_NOT_READY: Kein Installationsjournal. Erst Mods vollständig installieren.')
    journal=json.loads(journal_file.read_text(encoding='utf-8'))
    if journal.get('schema')!=1 or journal.get('status')!='INSTALLED' or Path(journal.get('game','')).absolute()!=root:
        raise BuildError('START_NOT_READY: Unvollständige oder unpassende Installation. Sicherung/Diagnose prüfen.')
    if info['active_data_archives'] or not info['prepared_structure']:
        raise BuildError('START_NOT_READY: Originalarchive wieder aktiv oder lose Spieldaten fehlen. Nicht als Modbuild starten.')
    if journal.get('exe_sha256') and journal['exe_sha256']!=info['exe_sha256']:
        raise BuildError('START_NOT_READY: Spiel-EXE nach Installation verändert. Erneut prüfen, keine automatische EXE-Ersetzung.')
    entries=journal.get('entries',[])
    if not entries or len(entries)>160_000:raise BuildError('START_NOT_READY: Ungültiges oder leeres Installationsjournal.')
    checked_entries([e['path'] for e in entries])
    mismatches=[]
    for i,e in enumerate(entries):
        check_cancel(log)
        p=casepath(root,safe_rel(e['path']))
        if not p.is_file() or digest(p)!=e.get('after'):mismatches.append(e['path'])
        if i%100==0 or i+1==len(entries):progress(log,i+1,len(entries))
    if mismatches:
        stage(log,'verify','error',f'{len(mismatches)} installierte Dateien fehlen oder wurden verändert')
        raise BuildError('START_NOT_READY: '+str(len(mismatches))+' installierte Dateien fehlen oder sind verändert: '
                         +', '.join(mismatches[:5])+'. Keine fremden Änderungen automatisch überschrieben.')
    warnings=[]
    if state.get('options',{}).get('graphics'):
        warnings.append('ReShade-Preset abgelegt. ReShade-Runtime und aktive Effekte sind nicht automatisch geprüft.')
    result={'status':'FILES_VERIFIED_NOT_GAME_TESTED','can_launch':True,'checked_files':len(entries),
            'checked_at':now(),'game':info['path'],'exe':info['exe'],'exe_sha256':info['exe_sha256'],
            'journal_sha256':digest(journal_file),'warnings':warnings,'game_tested':False}
    stage(log,'verify','done',f'{len(entries)} installierte Dateien geprüft · Spieltest noch offen',len(entries),len(entries))
    stage(log,'launch','waiting','Dateiprüfung bestanden. „Spiel starten“ öffnet genau diesen Spielordner.')
    return result


def launch_selected(base,log=print):
    if os.name!='nt':raise BuildError('Spielstart ist nur unter Windows möglich.')
    from engine import Engine
    from processes import game_running
    from steps import stage
    engine=Engine(Path(base));game=engine.state.get('installed_game') or engine.state.get('game','')
    selected=engine.state.get('game')
    if selected and Path(selected).absolute()!=Path(game).absolute():
        raise BuildError('START_NOT_READY: Ausgewählter Spielordner und installierter Build unterscheiden sich. Richtige Kopie im Assistenten auswählen.')
    ready=verify_installation(game,engine.state,log)
    if game_running():raise BuildError('TCS läuft bereits. Vor einem weiteren Start schließen.')
    exe=no_links(Path(ready['exe']))
    # Do not use a generic Steam URI: that can start a different vanilla copy.
    # This is the user's ORIGINAL executable; no crack, patch or alternate binary.
    process=subprocess.Popen([str(exe)],cwd=ready['game'],shell=False)
    ready.update(launch_requested=True,pid=process.pid,launch_requested_at=now())
    engine.state['readiness']=ready;engine.save()
    stage(log,'launch','waiting','Startbefehl gesendet. Im Spiel Mods prüfen und Erfolg bestätigen.')
    return {'launched':True,'pid':process.pid,'game_tested':False,
            'note':'Original-EXE aus dem geprüften Spielordner gestartet. Steam ggf. geöffnet lassen; sichtbarer Start/Mods noch nicht bestätigt.'}


def main():
    base=Path(__file__).resolve().parents[1]
    try:
        print('TCS Remaster: installierte Dateien prüfen und ausgewählten Build starten.',flush=True)
        launch_selected(base)
        return 0
    except Exception as exc:
        print('Spiel nicht gestartet: '+str(exc),flush=True)
        if sys.stdin.isatty():input('Eingabe drücken. Danach STARTEN.cmd → Diagnose/Installation prüfen.')
        return 1

if __name__=='__main__':raise SystemExit(main())
