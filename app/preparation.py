"""Transactional loose-file preparation of a user's own PC Game*.DAT archives.
No executable patching, no key handling and no savegame deletion. QuickBMS runs
without administrative rights, first in list mode, then in an isolated staging
folder. This is path isolation, not an OS sandbox. Real-game validation is pending.
"""
from __future__ import annotations
import json
import hashlib
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from engine import casepath, describe_game, digest, jsonwrite, within, EXE, META
from safety import BuildError, MAX_BYTES, MAX_FILES, BLOCKED, checked_entries, no_links, safe_rel
from nettools import Tools, run_process
from tt_pak import inspect_pak, extract_raw, patched_deflate_script, POLICY as PAK_POLICY

PREP_META = '.tcs-preparation'
LIST_ROW = re.compile(r'^\s*[0-9a-fA-F]{8,16}\s+(\d+)\s+(.+?)\s*$')


from diagnostics import check_cancel, phase, progress

# These are ORIGINAL archives, not mod packages. They can contain copies of
# runtime DLLs/EXEs. Never install those copies and never relax safety.BLOCKED.
ORIGINAL_DATA_POLICY = 'original-data-only-v1'


class ExtractedFiles(dict):
    """Data records plus an audit of files deliberately not extracted."""
    def __init__(self, records=(), *, excluded=(), format_info=None):
        super().__init__(records)
        self.excluded = list(excluded)
        self.format_info = dict(format_info or {})


def data_extraction_filter() -> str:
    """Static QuickBMS -f rules. No archive-controlled text becomes an option.

    QuickBMS documents {} as a wildcard, ; as a separator and ! as exclusion.
    See https://aluigi.altervista.org/papers/quickbms.txt, section 2.
    The complete listing is validated BEFORE this extraction filter is used.
    """
    return ';'.join(['{}', *('!{}' + ext for ext in sorted(BLOCKED))])


def parse_listing(text: str, *, original_data: bool = False,
                  excluded: list | None = None) -> dict[str, dict]:
    """Validate every path/size, then omit runtime code ONLY in original mode.

    Strict mode is kept as the default. Excluded entries still count towards
    archive limits and duplicate/path-collision checks. An unsafe path is never
    rescued by its .dll suffix. Administrative directories remain an error.
    """
    if not isinstance(text, str):
        raise BuildError('QuickBMS-Dateiliste fehlt oder ist nicht lesbar.')
    result = {}; total = 0; seen = {}; skipped = []
    if re.search(r'Alert:|\bError:|contact me|crc.+not been found', text, re.I):
        raise BuildError('QuickBMS meldet eine unsichere Archivzuordnung. Nicht automatisch installieren.')
    for line in text.splitlines():
        m = LIST_ROW.match(line)
        if not m: continue
        size = int(m.group(1)); rel = safe_rel(m.group(2).replace('\\', '/'))
        if any(part.startswith('.') for part in rel.split('/')):
            raise BuildError('Administrativer Dateipfad im Datenarchiv: ' + rel)
        key = rel.casefold()
        if key in seen:
            raise BuildError('Mehrdeutiger Dateipfad im Archiv: ' + rel)
        seen[key] = rel; total += size
        if len(seen) > MAX_FILES or total > MAX_BYTES:
            raise BuildError('Extraktionslimit überschritten.')
        row = {'path': rel, 'bytes': size}
        if Path(rel).suffix.lower() in BLOCKED:
            if not original_data:
                raise BuildError('Ausführbare oder administrative Datei im Datenarchiv: ' + rel)
            skipped.append({**row, 'reason': 'runtime-or-script', 'action': 'not-extracted'})
        else:
            result[key] = row
    if not seen:
        raise BuildError('QuickBMS lieferte keine sicher lesbare Dateiliste. Keine Spieländerung erfolgt.')
    checked_entries(list(seen.values()))
    if excluded is not None:
        excluded.extend(skipped)
    return result


def _log_exclusions(excluded: list, log, archive: str = ''):
    reporter = getattr(log, 'original_filter', None)
    if callable(reporter):
        reporter(archive, excluded)
    if not excluded: return
    log(f'{len(excluded)} Laufzeit-/Skriptdatei(en) im Originalarchiv ausgelassen. '
        'Vorhandene EXE-/DLL-Dateien bleiben unverändert; nichts manuell löschen.')
    for row in excluded[:20]:
        log('Nicht entpacken / nicht installieren: ' + row['path'])
    if len(excluded) > 20:
        log(f'Weitere {len(excluded)-20} Einträge stehen im lokalen Originaldaten-Prüfbericht.')


def _checked_exclusions(rows) -> list:
    """Validate cached audit metadata; it never authorises copying any file."""
    if not isinstance(rows, list) or len(rows) > MAX_FILES:
        raise BuildError('Ungültiger Ausschlussbericht im Extraktions-Zwischenstand.')
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise BuildError('Ungültiger Ausschlusseintrag.')
        rel = safe_rel(row['path']); size = row['bytes']
        if (Path(rel).suffix.lower() not in BLOCKED or
                any(p.startswith('.') for p in rel.split('/')) or
                type(size) is not int or not 0 <= size <= MAX_BYTES):
            raise BuildError('Ungültiger Ausschlusseintrag im Originalarchiv.')
        result.append({'path': rel, 'bytes': size, 'reason': 'runtime-or-script', 'action': 'not-extracted'})
    checked_entries([r['path'] for r in result])
    return result


def verify_extraction(folder: Path, listing: dict, log=lambda _:None) -> dict:
    # Defence in depth: even a changed cache or ignored QuickBMS filter cannot
    # introduce a DLL/EXE into the preparation manifest.
    for key, row in listing.items():
        rel = safe_rel(row['path'])
        if (key != rel.casefold() or Path(rel).suffix.lower() in BLOCKED or
                any(p.startswith('.') for p in rel.split('/')) or
                type(row['bytes']) is not int or row['bytes'] < 0):
            raise BuildError('Unzulässige Datei in der Spieldaten-Auswahl: ' + rel)
    checked_entries([r['path'] for r in listing.values()])
    actual = {}
    for p in folder.rglob('*'):
        check_cancel(log)
        no_links(p)
        if p.is_file():
            rel = safe_rel(p.relative_to(folder).as_posix()); key = rel.casefold()
            if key in actual:
                raise BuildError('Dateien unterscheiden sich nur in Groß-/Kleinschreibung.')
            if Path(rel).suffix.lower() in BLOCKED:
                raise BuildError('Entpackwerkzeug hat trotz Ausschluss eine Programmdatei erzeugt: '
                                 + rel + '. Keine Übernahme ins Spiel.')
            expected = listing.get(key)
            if not expected or p.stat().st_size != expected['bytes']:
                raise BuildError('Extraktionsinhalt weicht von der geprüften Dateiliste ab: ' + rel)
            actual[key] = {'path': rel, 'source': str(p), 'sha256': digest(p), 'bytes': p.stat().st_size}
    if set(actual) != set(listing):
        raise BuildError('Nicht alle aufgelisteten Spieldaten wurden extrahiert.')
    return actual


def _log_pak(index, log, method):
    summary = index.summary(method)
    reporter = getattr(log, 'pak_check', None)
    if callable(reporter): reporter(index.archive.name, summary)
    log(f'{index.archive.name}: PAK-Tabelle geprüft · {len(index.entries)} Einträge · '
        f'{summary["short_entries"]} kurze Einträge unter 32 Bytes · {method}.')
    return summary


def _extract_raw_pak(index, folder, log):
    check_cancel(log)
    phase(log, 'pak_validate', 'PAK-Einträge und Dateigrenzen prüfen: ' + index.archive.name)
    folder.mkdir(parents=True, exist_ok=False)
    listing = index.listing(); excluded = index.exclusions()
    _log_exclusions(excluded, log, index.archive.name)
    summary = _log_pak(index, log, 'native-raw')
    total = sum(r['bytes'] for r in listing.values())
    if shutil.disk_usage(folder).free < total + 512*1024**2:
        raise BuildError('Zu wenig Speicher für das vollständige PAK-Entpacken.')
    audit = folder.parent / (folder.name + '-original-audit.json')
    base = {'policy': ORIGINAL_DATA_POLICY, 'archive': index.archive.name,
            'data_files': len(listing), 'excluded': excluded, 'format_info': summary}
    jsonwrite(audit, {**base, 'status': 'LISTED_ONLY'})
    phase(log, 'pak_extract', 'PAK-Spieldaten längengeprüft entpacken: ' + index.archive.name)
    extract_raw(index, folder, log)
    result = verify_extraction(folder, listing, log)
    jsonwrite(audit, {**base, 'status': 'VERIFIED'})
    return ExtractedFiles(result, excluded=excluded, format_info=summary)


def extract_one(exe: Path, script: Path, archive: Path, folder: Path, log=print):
    check_cancel(log)
    index = inspect_pak(archive, log)
    if index is not None and not index.needs_codec:
        return _extract_raw_pak(index, folder, log)
    format_info = {}; script_info = {}
    if index is not None:
        format_info = _log_pak(index, log, 'quickbms-bounded-dflt')
        # Only this proven PAK format needs the bounded routine. Keep the
        # downloaded script/receipt unchanged; validate all entry bounds first.
        folder.parent.mkdir(parents=True, exist_ok=True)
        derived = folder.parent / (folder.name + '-bounded.bms')
        script_info = patched_deflate_script(script, derived)
        script = derived
    phase(log, 'list_original', 'Originalarchiv auflisten: ' + archive.name)
    folder.mkdir(parents=True, exist_ok=False)
    listlog = folder.parent / (folder.name + '-list.log')
    run_process([str(exe), '-l', '-R', str(script), str(archive), str(folder)],
                cwd=str(folder), timeout=1800, log_file=listlog, log=log)
    if listlog.stat().st_size > 64*1024**2:
        raise BuildError('Werkzeugausgabe überschreitet das Limit.')
    excluded = []
    listing = parse_listing(listlog.read_text(encoding='utf-8', errors='replace'),
                            original_data=True, excluded=excluded)
    if index is not None:
        expected = index.listing()
        if ({k: r['bytes'] for k, r in listing.items()} !=
                {k: r['bytes'] for k, r in expected.items()} or
                {(r['path'].casefold(), r['bytes']) for r in excluded} !=
                {(r['path'].casefold(), r['bytes']) for r in index.exclusions()}):
            raise BuildError('QuickBMS-Dateiliste stimmt nicht mit der unabhängig geprüften PAK-Tabelle überein.')
    # This audit is outside the extraction directory, so it cannot be installed.
    audit = folder.parent / (folder.name + '-original-audit.json')
    jsonwrite(audit, {'policy': ORIGINAL_DATA_POLICY, 'archive': archive.name,
                     'data_files': len(listing), 'excluded': excluded,
                     'status': 'LISTED_ONLY', 'format_info': format_info, 'script_info': script_info})
    _log_exclusions(excluded, log, archive.name)
    if not listing:
        log(archive.name + ': nur ausgeschlossene Programmdateien; kein Entpacken erforderlich.')
        jsonwrite(audit, {'policy': ORIGINAL_DATA_POLICY, 'archive': archive.name,
                         'data_files': 0, 'excluded': excluded, 'status': 'VERIFIED_NO_DATA',
                         'format_info': format_info, 'script_info': script_info})
        return ExtractedFiles(excluded=excluded, format_info=format_info)
    total = sum(x['bytes'] for x in listing.values())
    if shutil.disk_usage(folder).free < total + 512*1024**2:
        raise BuildError('Zu wenig Speicher für das vollständige Entpacken.')
    phase(log, 'extract_data', 'Nur Spieldaten entpacken: ' + archive.name)
    log(f'{archive.name}: {len(listing):,} Spieldateien; {len(excluded):,} Programmdateien ausgeschlossen.')
    # No -Y, -C, -n, -p, -w, -S or reimport. Input is read-only; stdin is closed.
    # Always use the filter, even when the list currently contains no programs.
    extractlog = folder.parent / (folder.name + '-extract.log')
    run_process([str(exe), '-o', '-R', '-f', data_extraction_filter(),
                 str(script), str(archive), str(folder)],
                cwd=str(folder), timeout=3600, log_file=extractlog, log=log)
    if extractlog.stat().st_size > 64*1024**2:
        raise BuildError('Werkzeugausgabe überschreitet das Limit.')
    status = extractlog.read_text(encoding='utf-8', errors='replace')
    if re.search(r'Alert:|\bError:|contact me|crc.+not been found', status, re.I):
        raise BuildError('QuickBMS hat Warnungen gemeldet. Die Spielinstallation bleibt unverändert.')
    phase(log, 'verify_extraction', 'Entpackte Spieldaten kontrollieren: ' + archive.name)
    result = verify_extraction(folder, listing, log)
    jsonwrite(audit, {'policy': ORIGINAL_DATA_POLICY, 'archive': archive.name,
                     'data_files': len(result), 'excluded': excluded, 'status': 'VERIFIED',
                     'format_info': format_info, 'script_info': script_info})
    return ExtractedFiles(result, excluded=excluded, format_info=format_info)


def stage_preparation(game_path: str, local: Path, log=print, extractor=None, tools=None) -> Path:
    phase(log,'inspect','Spielordner, laufendes Spiel und Vorbereitung prüfen …')
    check_cancel(log)
    info=describe_game(game_path); game=Path(info['path'])
    if within(local,game) or within(game,local): raise BuildError('Installer und Spiel müssen getrennte Ordner sein.')
    if info['active_install']: raise BuildError('Zuerst die bestehende Modinstallation wiederherstellen.')
    if (game/PREP_META).exists(): raise BuildError('Vorbereitung existiert bereits. Status prüfen oder zurücksetzen.')
    archives=sorted([p for p in game.iterdir() if p.is_file() and re.fullmatch(r'game\d*\.dat',p.name,re.I)],key=lambda p:p.name.casefold())
    if not archives: raise BuildError('Keine unterstützten Game*.DAT-Archive gefunden. Eine bereits entpackte Kopie benötigt diesen Schritt nicht.')
    from engine import Engine
    if Engine._running(): raise BuildError('Das Spiel läuft. Vor der Vorbereitung schließen.')
    inputs=[]
    for p in archives:
        no_links(p); phase(log,'hash_originals','Originalarchiv prüfen: '+p.name)
        total=p.stat().st_size; count=0; h=hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda:f.read(4*1024*1024),b''):
                check_cancel(log); h.update(block); count+=len(block); progress(log,count,total,'Bytes')
        if count!=total: raise BuildError('Originalarchiv wurde während der Prüfung verändert.')
        inputs.append({'name':p.name,'sha256':h.hexdigest(),'bytes':count})
    key=hashlib.sha256(json.dumps({'game':str(game),'exe':info['exe_sha256'],'archives':inputs},sort_keys=True).encode()).hexdigest()[:32]
    work=no_links(local/'preparation'/key); work.mkdir(parents=True,exist_ok=True)
    ready=work/'manifest.json'
    if ready.is_file():
        phase(log,'verify_stage','Vorhandene vollständige Extraktion erneut prüfen …')
        validate_manifest(ready,local,log)
        log('Bereits vollständig vorbereitete Originaldaten werden wiederverwendet. Kein erneutes Entpacken nötig.')
        return ready
    if extractor is None:
        tool_pair = None
        def extractor(a, o, l):
            nonlocal tool_pair
            # Reused caches and raw PAKs need no fresh tool download.
            index = inspect_pak(a, l)
            if index is not None and not index.needs_codec:
                return _extract_raw_pak(index, o, l)
            if tool_pair is None:
                tool_pair = (tools or Tools(local)).quickbms(l)
            return extract_one(*tool_pair, a, o, l)
    raw_extractor=extractor
    def cached_extract(archive,folder,log):
        check_cancel(log)
        receipt=no_links(folder.parent/(folder.name+'-verified.json'))
        source_hash=digest(archive)
        if receipt.is_file() and folder.is_dir():
            try:
                saved=json.loads(receipt.read_text(encoding='utf-8'))
                if saved.get('archive_sha256')==source_hash and isinstance(saved.get('files'),dict):
                    phase(log,'verify_stage','Vorherige Extraktion prüfen: '+archive.name)
                    listing={k:{'path':r['path'],'bytes':r['bytes']} for k,r in saved['files'].items()}
                    actual=verify_extraction(folder,listing,log)
                    pak_index = inspect_pak(archive, log)
                    format_info = saved.get('format_info', {})
                    if pak_index is not None:
                        if ({k:r['bytes'] for k,r in listing.items()} !=
                                {k:r['bytes'] for k,r in pak_index.listing().items()}):
                            raise BuildError('PAK-Zwischenstand passt nicht zu seiner Dateitabelle.')
                        format_info = _log_pak(pak_index, log, 'verified-cache')
                    if all(actual[k]['sha256']==r['sha256'] for k,r in saved['files'].items()):
                        log('Geprüfter Teilschritt wiederverwendet: '+archive.name)
                        excluded = _checked_exclusions(saved.get('excluded', []))
                        _log_exclusions(excluded, log, archive.name)
                        return ExtractedFiles(actual, excluded=excluded, format_info=format_info)
            except (OSError,ValueError,KeyError,TypeError):
                check_cancel(log)
                log('Unvollständigen Extraktions-Zwischenstand neu aufbauen: '+archive.name)
        # Only this installer's isolated scratch folder, never the original game.
        if not within(folder,work) or folder==work: raise BuildError('Ungültiger Extraktions-Arbeitsordner.')
        no_links(folder)
        if folder.exists(): shutil.rmtree(folder)
        receipt.unlink(missing_ok=True)
        result=raw_extractor(archive,folder,log)
        jsonwrite(receipt, {'archive_sha256': source_hash, 'files': result,
                            'policy': ORIGINAL_DATA_POLICY,
                            'excluded': _checked_exclusions(getattr(result, 'excluded', [])),
                            'format_info': getattr(result, 'format_info', {})})
        return result
    extractor=cached_extract
    merged={}; containers=0; merged_bytes=0; excluded_originals=[]; archive_checks=[]
    def ingest(records,depth=0,parent='',origin=''):
        nonlocal containers, merged_bytes
        if depth>4: raise BuildError('Zu viele verschachtelte Originalarchive. Automatische Vorbereitung gestoppt.')
        format_info = getattr(records, 'format_info', {})
        if format_info:
            archive_checks.append({'archive': origin, **format_info})
        for omitted in _checked_exclusions(getattr(records, 'excluded', [])):
            excluded_originals.append({**omitted, 'archive': origin})
        if len(excluded_originals) > MAX_FILES:
            raise BuildError('Zu viele ausgeschlossene Originaldateien.')
        for row in records.values():
            check_cancel(log)
            original=row['path']; rel=safe_rel(parent+'/'+original if parent else original)
            source=Path(row['source'])
            if Path(rel).suffix.lower() in BLOCKED or any(p.startswith('.') for p in rel.split('/')):
                raise BuildError('Unzulässige Programmdatei im Extraktionsergebnis: ' + rel)
            if source.suffix.lower() in ('.pak','.fpk'):
                containers+=1
                if containers>2000: raise BuildError('Zu viele Unterarchive.')
                log('Unterarchiv prüfen: '+rel)
                nested=extractor(source,work/('nested-'+str(containers)),log)
                # Some bundles store game-root paths, others paths relative to the bundle.
                top={x['path'].split('/')[0].casefold() for x in nested.values()}
                base='' if top & {'chars','stuff','levels','audio','movies'} else str(Path(rel).parent).replace('\\','/')
                if base=='.': base=''
                ingest(nested,depth+1,base,rel)
                continue
            key=rel.casefold(); candidate={**row,'path':rel}
            if key in merged and merged[key]['sha256']!=candidate['sha256']:
                raise BuildError('Originalarchive enthalten verschiedene Fassungen desselben Pfads: '+rel+'. Keine Archiv-Reihenfolge geraten.')
            if key not in merged:
                merged[key]=candidate; merged_bytes+=candidate['bytes']
            if len(merged)>MAX_FILES or merged_bytes>MAX_BYTES:
                raise BuildError('Grenze für entpackte Spieldaten überschritten.')
    for n,archive in enumerate(archives):
        no_links(archive)
        records=extractor(archive,work/f'archive-{n:02}',log)
        ingest(records,origin=archive.name)
    roots={v['path'].split('/')[0].lower() for v in merged.values()}
    if not {'chars','stuff','levels'}<=roots:
        raise BuildError('CHARS, STUFF und LEVELS fehlen im Extraktionsergebnis. Das Spiel bleibt unverändert.')
    # Protect executables, existing unknown loose mods and changed originals.
    for row in merged.values():
        dest=casepath(game,row['path'])
        if dest.exists() and (not dest.is_file() or digest(dest)!=row['sha256']):
            raise BuildError('Abweichende vorhandene lose Datei: '+row['path']+'. Unbekannte Mods werden nicht überschrieben.')
    manifest={'schema':1,'game':str(game),'exe_sha256':info['exe_sha256'],'archives':inputs,
              'files':list(merged.values()),'status':'STAGED_ONLY','windows_game_tested':False,
              'data_policy': ORIGINAL_DATA_POLICY, 'excluded_original_files': excluded_originals,
              'archive_checks': archive_checks}
    path=work/'manifest.json'; jsonwrite(path,manifest)
    log('Originaldateien vollständig geprüft; Installation noch unverändert.')
    return path


def check_writable(game: Path) -> bool:
    p=game/('.tcs-write-test-'+uuid.uuid4().hex)
    try:
        with p.open('xb') as f: f.write(b'')
        p.unlink(); return True
    except PermissionError: return False


def validate_manifest(path: Path, local: Path, log=lambda _:None):
    path=no_links(path.absolute())
    if not within(path,local/'preparation') or path.name!='manifest.json':
        raise BuildError('Vorbereitungsmanifest stammt nicht aus diesem Arbeitsordner.')
    m=json.loads(path.read_text(encoding='utf-8'))
    if m.get('schema')!=1 or not isinstance(m.get('files'),list) or not 0<len(m['files'])<=MAX_FILES:
        raise BuildError('Ungültiges Vorbereitungsmanifest.')
    game=no_links(Path(m['game']))
    if within(game,local) or within(local,game): raise BuildError('Spiel und Arbeitsordner überschneiden sich.')
    if describe_game(str(game))['exe_sha256']!=m['exe_sha256']: raise BuildError('Spiel-EXE wurde inzwischen verändert.')
    keys=set(); size=0
    for i,r in enumerate(m['files']):
        if i%200==0:
            check_cancel(log); progress(log,i,len(m['files']))
        rel=safe_rel(r['path']); key=rel.casefold()
        if key in keys or any(p.startswith('.') for p in rel.split('/')) or Path(rel).suffix.lower() in BLOCKED:
            raise BuildError('Ungültiger Zielpfad im Vorbereitungsmanifest.')
        keys.add(key); size+=r['bytes']
        p=no_links(Path(r['source']))
        if not within(p,path.parent) or not p.is_file() or digest(p)!=r['sha256'] or p.stat().st_size!=r['bytes']:
            raise BuildError('Vorbereitete Spieldaten wurden seit der Prüfung verändert.')
        dest=casepath(game,rel)
        if dest.exists() and (not dest.is_file() or digest(dest)!=r['sha256']): raise BuildError('Spielziel inzwischen verändert: '+rel)
    if size>MAX_BYTES: raise BuildError('Vorbereitungsmanifest überschreitet das Größenlimit.')
    archive_keys=set()
    for r in m['archives']:
        name=safe_rel(r['name'])
        if not re.fullmatch(r'game\d*\.dat',name,re.I) or name.casefold() in archive_keys:
            raise BuildError('Ungültige oder doppelte Originalarchiv-Zuordnung.')
        archive_keys.add(name.casefold())
        p=casepath(game,name)
        if not p.is_file() or digest(p)!=r['sha256']: raise BuildError('Originalarchiv inzwischen verändert: '+name)
    if not archive_keys: raise BuildError('Vorbereitungsmanifest ohne Originalarchive.')
    return m,game


def commit_preparation(path: Path, local: Path, log=print, fail_after=None):
    phase(log,'verify_stage','Vorbereitete Spieldaten vor dem Schreiben prüfen …')
    m,game=validate_manifest(path,local,log)
    check_cancel(log)
    from engine import Engine
    if Engine._running(): raise BuildError('Spiel läuft. Keine Änderungen vorgenommen.')
    meta=no_links(game/PREP_META)
    if meta.exists(): raise BuildError('Vorbereitung/Backup bereits vorhanden. Zuerst wiederherstellen.')
    if not check_writable(game): raise PermissionError('Für diesen Spielordner ist eine Windows-Freigabe erforderlich.')
    total=sum(r['bytes'] for r in m['files'])
    if shutil.disk_usage(game).free<total+512*1024**2: raise BuildError('Nicht genug Speicher im Spiel-Laufwerk.')
    phase(log,'commit_originals','Originaldaten bereitstellen und DAT-Backups erstellen …')
    meta.mkdir(); (meta/'original-archives').mkdir()
    # Full write-ahead journal before modifying any game data.
    journal={'schema':1,'game':str(game),'exe_sha256':m['exe_sha256'],'status':'PREPARING',
             'files':[{**r,'created':not casepath(game,r['path']).exists()} for r in m['files']],
             'archives':m['archives'],'created_dirs':[],
             'excluded_original_files':m.get('excluded_original_files',[]),'data_policy':ORIGINAL_DATA_POLICY}
    missing_dirs=set()
    for r in journal['files']:
        if not r['created']: continue
        parent=casepath(game,r['path']).parent
        while parent!=game and not parent.exists():
            missing_dirs.add(parent.relative_to(game).as_posix());parent=parent.parent
    journal['created_dirs']=sorted(missing_dirs,key=lambda d:(len(d.split('/')),d))
    # Directory rollback metadata is written once before any game writes.
    jsonwrite(meta/'journal.json',journal)
    operations=0
    try:
        for index,r in enumerate(journal['files']):
            if index%300==0:
                log(f'Spieldaten bereitstellen: {index+1}/{len(journal["files"])}')
                progress(log,index+1,len(journal['files']))
            if not r['created']: continue
            dest=casepath(game,r['path'])
            dest.parent.mkdir(parents=True,exist_ok=True)
            temp=no_links(meta/'pending-file')
            shutil.copyfile(r['source'],temp)
            if digest(temp)!=r['sha256']: raise BuildError('Kopierprüfung fehlgeschlagen.')
            if dest.exists(): raise BuildError('Datei wurde während der Vorbereitung neu angelegt: '+r['path'])
            os.replace(temp,dest)
            operations+=1
            if fail_after is not None and operations>=fail_after: raise BuildError('Injected preparation failure')
        # Only now remove original archives from the loader path; keep them in a backup.
        for r in m['archives']:
            src=casepath(game,r['name']); backup=meta/'original-archives'/r['name']
            if digest(src)!=r['sha256']: raise BuildError('Originalarchiv während der Vorbereitung verändert.')
            os.replace(src,backup)
        journal['status']='PREPARED_NOT_GAME_TESTED'; jsonwrite(meta/'journal.json',journal)
        phase(log, 'prepared_data', 'Spieldaten vorbereitet · Programmdateien unverändert')
        log('Vorbereitung abgeschlossen: EXE unverändert; Original-DATs gesichert; Spielstände nicht angefasst.')
        return {'prepared':True,'status':journal['status'],'game':str(game),'files':len(journal['files']),
                'excluded_original_count':len(journal.get('excluded_original_files',[]))}
    except Exception:
        restore_preparation(str(game),log)
        raise


def restore_preparation(game_path: str, log=print):
    game=no_links(Path(game_path)); meta=no_links(game/PREP_META); jf=meta/'journal.json'
    if not jf.is_file(): raise BuildError('Kein Vorbereitungsbackup vorhanden.')
    if (game/META/'journal.json').exists(): raise BuildError('Erst die Modinstallation zurücksetzen, danach die Originalvorbereitung.')
    from engine import Engine
    if Engine._running(): raise BuildError('Spiel vor der Wiederherstellung schließen.')
    j=json.loads(jf.read_text(encoding='utf-8'))
    # Preflight all later modifications before any destructive action.
    for r in j['files']:
        if not r['created']: continue
        dest=casepath(game,r['path'])
        if dest.exists() and (not dest.is_file() or digest(dest)!=r['sha256']):
            raise BuildError('Seit der Vorbereitung verändert; Wiederherstellung pausiert: '+r['path'])
    for r in j['archives']:
        src=no_links(meta/'original-archives'/safe_rel(r['name'])); dest=casepath(game,r['name'])
        if src.exists() and digest(src)!=r['sha256']: raise BuildError('Originalbackup verändert.')
        if dest.exists() and digest(dest)!=r['sha256']: raise BuildError('Originalarchiv am Ziel wurde verändert.')
        if not src.exists() and not dest.exists(): raise BuildError('Originalarchiv und Backup fehlen.')
    for r in j['archives']:
        src=meta/'original-archives'/r['name']; dest=casepath(game,r['name'])
        if src.exists() and not dest.exists(): os.replace(src,dest)
    for r in reversed(j['files']):
        if r['created']: casepath(game,r['path']).unlink(missing_ok=True)
    for d in reversed(j['created_dirs']):
        p=casepath(game,d)
        try: p.rmdir()
        except OSError: pass
    shutil.rmtree(meta)
    log('Original-DATs wiederhergestellt. Spielstände und EXE unverändert.')
    return {'restored':True,'kind':'original-preparation'}
