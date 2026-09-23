"""Update only this installer's allowlisted program files. Never game data.
Old .local, imported archives, .runtime, Windows registrations and savegames stay
where they are. Existing program files are backed up, then atomically replaced.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from engine import digest, jsonwrite, within
from safety import BuildError, no_links, safe_rel, checked_entries

BASE=Path(__file__).resolve().parents[1]


def workspace_running(target:Path) -> bool:
    connection=target/'.local'/'connection.json'
    if not connection.is_file():return False
    try:
        data=json.loads(connection.read_text(encoding='utf-8'))
        match=re.fullmatch(r'http://127\.0\.0\.1:([0-9]+)/#[A-Za-z0-9_-]+',data.get('url',''))
        if not match:return True
        with socket.create_connection(('127.0.0.1',int(match.group(1))),timeout=1):return True
    except (ConnectionRefusedError,TimeoutError):return False
    except (OSError,ValueError,TypeError):return False


def checked_package(source:Path):
    source=no_links(source)
    data=json.loads((source/'publish-allowlist.json').read_text(encoding='utf-8'))
    names=data.get('files')
    if not isinstance(names,list) or not 1<=len(names)<=400:raise BuildError('Ungültige Paketdateiliste.')
    checked_entries(names)
    checks={}
    for line in (source/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        match=re.fullmatch(r'([a-f0-9]{64})  (.+)',line)
        if not match:raise BuildError('Ungültige Paket-Prüfsummenliste.')
        checks[safe_rel(match[2])]=match[1]
    for name in names:
        rel=safe_rel(name)
        if rel.split('/')[0] in {'.local','.runtime','inbox','downloads'}:raise BuildError('Private Dateien dürfen nicht Teil eines Updates sein.')
        path=no_links(source/rel)
        if not path.is_file():raise BuildError('Update-Datei fehlt: '+rel)
        if rel!='SHA256SUMS.txt' and (checks.get(rel)!=digest(path)):raise BuildError('Update-Datei beschädigt oder verändert: '+rel)
    return names


def apply_update(source:Path,target:Path,log=print,*,fail_after=None):
    source=no_links(source);target=no_links(target)
    if source==target or within(source,target) or within(target,source):raise BuildError('Alten und neuen Installer in getrennten Ordnern entpacken.')
    if (target/'LEGOStarWarsSaga.exe').exists():raise BuildError('Das ist der Spielordner. Für das Update den alten TCS-Installerordner wählen.')
    if not (target/'app'/'server.py').is_file() or not (target/'profile.json').is_file():raise BuildError('Kein vorhandener TCS-Installer in diesem Ordner.')
    old=json.loads((target/'profile.json').read_text(encoding='utf-8'))
    if old.get('name')!='TCS Remaster · Classic Plus':raise BuildError('Der Zielordner gehört nicht zu diesem Installer.')
    if workspace_running(target):raise BuildError('Der alte Assistent läuft noch. Im alten Fenster „Assistent beenden“ klicken und Update erneut starten.')
    names=checked_package(source)
    for rel in names:
        p=no_links(target/rel)
        if p.exists() and not p.is_file():raise BuildError('Ein Ordner blockiert eine Update-Datei: '+rel)
    size=sum((source/rel).stat().st_size+(target/rel).stat().st_size if (target/rel).is_file() else (source/rel).stat().st_size for rel in names)
    if shutil.disk_usage(target).free<size+64*1024**2:raise BuildError('Nicht genug Speicher für das gesicherte Installer-Update.')
    backup=no_links(target/'.local'/'update-backups'/('0.4.0-'+uuid.uuid4().hex[:10]));backup.mkdir(parents=True)
    journal={'schema':1,'files':[],'status':'PREPARING'}
    for rel in names:
        dest=target/rel
        entry={'path':rel,'before':digest(dest) if dest.is_file() else None,'after':digest(source/rel)}
        if dest.is_file():
            p=backup/'files'/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dest,p)
            if digest(p)!=entry['before']:raise BuildError('Update-Sicherung fehlgeschlagen: '+rel)
        journal['files'].append(entry)
    jsonwrite(backup/'journal.json',journal)
    applied=[]
    try:
        for i,entry in enumerate(journal['files']):
            rel=entry['path'];dest=no_links(target/rel)
            if (digest(dest) if dest.is_file() else None)!=entry['before']:raise BuildError('Installer wurde während des Updates verändert: '+rel)
            dest.parent.mkdir(parents=True,exist_ok=True)
            fd,tmp=tempfile.mkstemp(prefix='update-',dir=backup);os.close(fd)
            try:
                shutil.copyfile(source/rel,tmp)
                if digest(Path(tmp))!=entry['after']:raise BuildError('Update-Kopierprüfung fehlgeschlagen: '+rel)
                os.replace(tmp,dest)
            finally:Path(tmp).unlink(missing_ok=True)
            applied.append(entry)
            if i%10==0:log(f'Programmdateien aktualisieren: {i+1}/{len(names)}')
            if fail_after is not None and len(applied)>=fail_after:raise BuildError('Synthetic update failure')
        journal['status']='UPDATED';jsonwrite(backup/'journal.json',journal)
        return {'target':str(target),'backup':str(backup),'files':len(applied),'status':'UPDATED_INSTALLER_ONLY'}
    except Exception:
        for entry in reversed(applied):
            dest=target/entry['path']
            if digest(dest)!=entry['after']:raise BuildError('Update-Rücknahme pausiert: Datei inzwischen extern verändert. Backups erhalten.')
            if entry['before']:shutil.copyfile(backup/'files'/entry['path'],dest)
            else:dest.unlink()
        journal['status']='ROLLED_BACK';jsonwrite(backup/'journal.json',journal)
        raise


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--target');args=parser.parse_args()
    try:
        print('TCS Installer 0.4.0 aktualisieren\nDen ALTEN Installerordner wählen, NICHT den Spielordner.\nDownloads, Einstellungen und Backups bleiben erhalten.',flush=True)
        if args.target:target=Path(args.target)
        else:
            from server import picker
            result=picker('folder')
            if not result:return 0
            target=Path(result)
        print('Ziel: '+str(target),flush=True)
        if input('Nur Installer-Programmdateien mit Sicherung aktualisieren? JA eingeben: ').strip().upper()!='JA':return 0
        result=apply_update(BASE,target)
        print('Fertig. Installer aktualisiert. .local und .runtime bleiben unverändert nutzbar.\nSicherung: '+result['backup'],flush=True)
        if os.name=='nt':os.startfile(str(target/'STARTEN.cmd'),cwd=str(target))
        return 0
    except (OSError,ValueError) as exc:
        print('Update nicht abgeschlossen: '+str(exc),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
