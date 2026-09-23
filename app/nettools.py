"""Small, bounded HTTPS client and explicitly consented external tool setup.
Downloaded mod archives are data, never programs. Tool downloads use a separate,
fixed-source path; none of the tool/runtime caches are exported with the installer.
"""
from __future__ import annotations
import hashlib
import http.client
import time
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from safety import BuildError, MAX_ARCHIVE, no_links, digest, safe_rel
from diagnostics import check_cancel, progress, phase

class NetworkError(BuildError):
    """A temporary network failure; bounded retries are permitted."""

USER_AGENT = 'TCSRemasterInstaller/0.4.0 (+local community installer)'
API_HOST = 'api.nexusmods.com'
QUICKBMS_SHA256 = 'b9d4f9efb55692994cd42a491cfea11f86e3375a618b9bd771583ce40ddb3828'
QUICKBMS_URLS = (
    'https://aluigi.altervista.org/papers/quickbms.zip',
    'https://mirror.aluigi.org/papers/quickbms.zip',
    'https://github.com/LittleBigBug/QuickBMS/releases/download/0.12.0/quickbms_win.zip',
)
GITHUB_HOSTS = {'api.github.com', 'github.com', 'raw.githubusercontent.com',
                'objects.githubusercontent.com', 'release-assets.githubusercontent.com'}
TOOL_HOSTS = GITHUB_HOSTS | {'aluigi.altervista.org', 'mirror.aluigi.org', 'www.7-zip.org', '7-zip.org'}


def allowed_url(url: str, purpose: str = 'tool') -> str:
    if not isinstance(url,str) or not url: raise BuildError('Downloadadresse fehlt oder ist ungültig.')
    u = urllib.parse.urlsplit(url)
    host = (u.hostname or '').lower()
    if u.scheme != 'https' or u.username or u.password or u.fragment or u.port not in (None, 443):
        raise BuildError('Nur HTTPS-Downloads von freigegebenen Quellen sind erlaubt.')
    if purpose == 'api':
        okay = host == API_HOST
    elif purpose == 'mod':
        okay = (host in {'nexusmods.com', 'www.nexusmods.com'} or host.endswith('.nexusmods.com'))
    else:
        okay = host in TOOL_HOSTS
    if not okay:
        raise BuildError('Download-Host ist nicht freigegeben. Kein Download ausgeführt.')
    return url


class Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, purpose: str):
        self.purpose = purpose
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed_url(newurl, self.purpose)
        # API credentials must never cross origin, not even through a redirect.
        if self.purpose == 'api' and urllib.parse.urlsplit(req.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            raise BuildError('API-Weiterleitung auf einen fremden Host wurde blockiert.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(url: str, *, purpose='tool', headers=None):
    allowed_url(url, purpose)
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, **(headers or {})})
    try:
        return urllib.request.build_opener(Redirects(purpose)).open(request, timeout=45)
    except urllib.error.HTTPError as exc:
        messages = {401: 'Nexus-Schlüssel ungültig oder abgelaufen.', 403: 'Download nicht autorisiert. Bei kostenlosem Nexus-Konto den Autorendownload im Browser bestätigen.',
                    404: 'Die Datei ist unter dieser Quelle nicht mehr verfügbar.', 429: 'API-Limit erreicht. Später erneut versuchen.'}
        if exc.code in (408,500,502,503,504): raise NetworkError(f'Downloadserver vorübergehend nicht erreichbar (HTTP {exc.code}).') from None
        # Do not echo URL, signed key, API key, or response body in errors/logs.
        raise BuildError(messages.get(exc.code, f'Downloadserver antwortet mit HTTP {exc.code}.')) from None
    except (OSError, ValueError, urllib.error.URLError):
        raise NetworkError('HTTPS-Verbindung fehlgeschlagen. Internetverbindung oder Dateiquelle prüfen.') from None


def get_json(url: str, *, purpose='tool', headers=None):
    with open_url(url, purpose=purpose, headers=headers) as response:
        data = response.read(8 * 1024**2 + 1)
    if len(data) > 8 * 1024**2:
        raise BuildError('API-Antwort überschreitet das Größenlimit.')
    try:
        return json.loads(data)
    except (ValueError, UnicodeError):
        raise BuildError('Quelle hat keine gültige JSON-Antwort geliefert.') from None


def _download_once(url: str, target: Path, *, purpose='tool', expected_sha256=None,
             maximum=MAX_ARCHIVE, log=lambda _: None, headers=None) -> dict:
    check_cancel(log)
    if expected_sha256 is not None and (not isinstance(expected_sha256,str) or not re.fullmatch(r'[a-fA-F0-9]{64}',expected_sha256)):
        raise BuildError('Ungültige Download-Prüfsumme. Der Download wurde nicht gestartet.')
    target = no_links(target.absolute())
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise BuildError('Downloadziel existiert bereits; wird nicht überschrieben.')
    part = target.with_name(target.name + '.part')
    no_links(part)
    if part.exists():
        raise BuildError('Unvollständiger vorheriger Download vorhanden. Erneut mit neuem Ziel starten.')
    h = hashlib.sha256(); count = 0; last = 0
    try:
        with open_url(url, purpose=purpose, headers=headers) as response, part.open('xb') as f:
            length = response.headers.get('Content-Length')
            expected_bytes = int(length) if length and length.isdecimal() else None
            if expected_bytes and expected_bytes > maximum:
                raise BuildError('Download ist größer als das zugelassene Limit.')
            if expected_bytes and shutil.disk_usage(target.parent).free < expected_bytes + 256*1024**2:
                raise BuildError('Nicht genug freier Speicher für diesen Download.')
            log('Download verbunden. Daten werden empfangen und geprüft …')
            while True:
                check_cancel(log)
                b = response.read(1024 * 1024)
                if not b: break
                count += len(b)
                progress(log,count,expected_bytes,'Bytes')
                if count > maximum: raise BuildError('Download-Größenlimit überschritten.')
                h.update(b); f.write(b)
                if count-last >= 32*1024**2:
                    log(f'{count//1024**2} MiB heruntergeladen …'); last=count
            f.flush(); os.fsync(f.fileno())
        if count == 0 or (expected_bytes is not None and count != expected_bytes):
            raise BuildError('Unvollständiger Download; keine Datei übernommen.')
        checksum = h.hexdigest()
        if expected_sha256 and checksum != expected_sha256.lower():
            raise BuildError('SHA-256 stimmt nicht mit der freigegebenen Prüfsumme überein. Datei verworfen.')
        os.replace(part, target)
        return {'sha256': checksum, 'bytes': count, 'hash_verified': bool(expected_sha256)}
    except (http.client.IncompleteRead, ConnectionError, TimeoutError, urllib.error.URLError):
        raise NetworkError('Verbindung während des Downloads unterbrochen. Die unvollständige Datei wird nicht verwendet.') from None
    finally:
        part.unlink(missing_ok=True)


def download(url: str, target: Path, *, purpose='tool', expected_sha256=None,
             maximum=MAX_ARCHIVE, log=lambda _: None, headers=None) -> dict:
    """Retry only transient network errors, never hash mismatches or permission errors."""
    for attempt in range(3):
        check_cancel(log)
        try:
            return _download_once(url,target,purpose=purpose,expected_sha256=expected_sha256,
                                  maximum=maximum,log=log,headers=headers)
        except NetworkError:
            if attempt==2: raise
            log(f'Verbindung unterbrochen. Automatischer neuer Versuch {attempt+2}/3 …')
            for _ in range((attempt+1)*4):
                check_cancel(log); time.sleep(0.25)


def require_windows():
    if os.name != 'nt':
        raise BuildError('Dieser Einrichtungsschritt ist nur unter Windows verfügbar.')


def run_process(args: list[str], *, cwd=None, timeout=180, log_file: Path | None=None, log=lambda _: None):
    """Bounded byte output with a heartbeat. Only read/staging tools are run here."""
    check_cancel(log)
    own_temp=log_file is None
    output=tempfile.TemporaryFile('w+b') if own_temp else no_links(log_file).open('w+b')
    process=None; started=time.monotonic(); last_notice=started
    try:
        kwargs={'creationflags':0x08000000} if os.name=='nt' else {}
        process=subprocess.Popen(args,cwd=cwd,stdin=subprocess.DEVNULL,stdout=output,
                                 stderr=subprocess.STDOUT,shell=False,**kwargs)
        while process.poll() is None:
            check_cancel(log)
            elapsed=time.monotonic()-started
            if elapsed>timeout:
                raise BuildError('Werkzeug-Zeitlimit erreicht. Bereits vollständig geprüfte Extraktionen bleiben für einen erneuten Versuch erhalten.')
            if os.fstat(output.fileno()).st_size>80*1024**2:
                raise BuildError('Werkzeugausgabe überschreitet die Sicherheitsgrenze.')
            if time.monotonic()-last_notice>=10:
                log(f'Werkzeug arbeitet weiterhin · {int(elapsed)} Sekunden. Bitte Fenster offen lassen.')
                last_notice=time.monotonic()
            time.sleep(0.25)
        if os.fstat(output.fileno()).st_size>80*1024**2:
            raise BuildError('Werkzeugausgabe überschreitet die Sicherheitsgrenze.')
        if process.returncode:
            output.seek(0,2);size=output.tell();output.seek(max(0,size-4000))
            tail=output.read().decode('utf-8',errors='replace')
            log('Werkzeugausgabe (letzte Zeilen):\n'+tail)
            raise BuildError(f'Werkzeug meldet Fehlercode {process.returncode}. Die letzten Werkzeugmeldungen stehen im Diagnosebereich.')
        output.seek(0)
        return output.read() if own_temp else None
    except OSError:
        raise BuildError('Werkzeug konnte nicht gestartet werden. Download bzw. Quarantäne in Windows-Sicherheit prüfen. Der Schutz wird nicht deaktiviert.') from None
    finally:
        if process is not None and process.poll() is None:
            process.kill(); process.wait(timeout=10)
        output.close()


def validate_script(text: str) -> None:
    """Reject dangerous interpreter capabilities; this is not a sandbox proof."""
    forbidden = re.compile(
        r'^\s*(?:(?:calldll|execute|system|include)\b|'
        r'(?:comtype|encryption)\s+[\"\']?execute\b)', re.I | re.M)
    if "Traveller's Tales" not in text or 'EXTRACT_FILE' not in text or forbidden.search(text):
        raise BuildError('Unerwarteter Skriptinhalt. Automatische Vorbereitung abgebrochen.')


class Tools:
    def __init__(self, local: Path):
        self.local = local
        self.root = no_links(local/'tools'); self.root.mkdir(exist_ok=True)
    def quickbms(self, log=print) -> tuple[Path, Path]:
        require_windows()
        phase(log,'tools','Entpackwerkzeuge laden und Prüfsummen kontrollieren …')
        from engine import jsonwrite
        folder = self.root/'quickbms'; folder.mkdir(exist_ok=True)
        archive = no_links(folder/'quickbms.zip')
        if archive.exists() and digest(archive) != QUICKBMS_SHA256:
            raise BuildError('Lokales QuickBMS-Archiv hat eine unerwartete Prüfsumme. Keine Ausführung.')
        if not archive.exists():
            partial=no_links(folder/'quickbms.zip.part')
            if partial.is_file():
                partial.unlink(); log('Unvollständigen Werkzeugdownload entfernt; sauberer Neuversuch.')
            for url in QUICKBMS_URLS:
                try:
                    log('QuickBMS herunterladen und gegen fest hinterlegte SHA-256 prüfen …')
                    download(url, archive, expected_sha256=QUICKBMS_SHA256, maximum=80*1024**2, log=log)
                    break
                except BuildError:
                    check_cancel(log)
                    log('Diese Quelle lieferte keine passende QuickBMS-Datei. Nächste freigegebene Quelle …')
            if not archive.exists():
                raise BuildError('QuickBMS 0.12 konnte nicht hash-verifiziert geladen werden. Im Werkzeugbereich ein offizielles quickbms.zip auswählen. Keine Spieländerung erfolgt.')
        with zipfile.ZipFile(archive) as z:
            names = [n for n in z.namelist() if Path(n).name.lower() == 'quickbms_4gb_files.exe']
            if len(names) != 1 or z.getinfo(names[0]).file_size > 64*1024**2:
                raise BuildError('Unerwarteter Inhalt im QuickBMS-Paket.')
            data = z.read(names[0])
        exe = no_links(folder/'quickbms_4gb_files.exe')
        if not data.startswith(b'MZ'): raise BuildError('QuickBMS-Binary ungültig.')
        exe.write_bytes(data)  # restored from verified archive on every use
        script = folder/'ttgames.bms'
        receipt = folder/'script-receipt.json'
        if script.exists() and receipt.exists():
            try:
                expected = json.loads(receipt.read_text(encoding='utf-8'))['sha256']
            except (KeyError,ValueError,OSError):
                raise BuildError('Skript-Prüfbeleg beschädigt. Den lokalen Werkzeugordner prüfen; Originalspiel bleibt unverändert.') from None
            if digest(script) != expected: raise BuildError('Lokales Extraktionsskript wurde verändert.')
        else:
            # Resolve a concrete commit first; fetch the script at that commit, not a floating raw URL.
            repo = 'linterniGamer/Tt-Games-quickbms-scripts'
            metadata = get_json(f'https://api.github.com/repos/{repo}/commits/main')
            commit = metadata.get('sha') if isinstance(metadata,dict) else None
            if not isinstance(commit,str) or not re.fullmatch(r'[0-9a-f]{40}', commit): raise BuildError('Skriptversion konnte nicht bestimmt werden.')
            script.unlink(missing_ok=True)
            result = download(f'https://raw.githubusercontent.com/{repo}/{commit}/files/ttgames.bms', script, maximum=256*1024,log=log)
            text = script.read_text(encoding='utf-8-sig')
            # The known script is a pure archive parser. No opt-in dangerous QuickBMS capabilities.
            try:
                validate_script(text)
            except BuildError:
                script.unlink(missing_ok=True)
                raise
            jsonwrite(receipt, {**result, 'repository':repo, 'commit':commit,
                               'trust':'HTTPS repository source; not an independently pinned script checksum'})
        validate_script(script.read_text(encoding="utf-8-sig"))
        return exe, script
    def import_quickbms(self, path: str):
        p = no_links(Path(path))
        if not p.is_file() or p.stat().st_size > 80*1024**2 or digest(p) != QUICKBMS_SHA256:
            raise BuildError('Benötigt das offizielle QuickBMS-Archiv mit der hinterlegten SHA-256. Andere Dateien bleiben unbenutzt.')
        folder=self.root/'quickbms'; folder.mkdir(exist_ok=True)
        shutil.copyfile(p, no_links(folder/'quickbms.zip'))
        return {'ready':True}
    def sevenzip(self, log=print) -> str:
        require_windows()
        from safety import find_7zip
        from engine import jsonwrite
        installed = find_7zip()
        if installed: return str(installed)
        folder = self.root/'7zip'; folder.mkdir(exist_ok=True)
        # Fixed official release, no third-party repack. GitHub asset digest required.
        metadata = get_json('https://api.github.com/repos/ip7z/7zip/releases/tags/26.03')
        if not isinstance(metadata,dict) or not isinstance(metadata.get('assets'),list): raise BuildError('Die offizielle Werkzeugliste ist momentan nicht lesbar. Später erneut versuchen.')
        assets=[a for a in metadata['assets'] if isinstance(a,dict) and a.get('name')=='7z2603-x64.msi']
        if len(assets)!=1 or not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', assets[0].get('digest') or ''):
            raise BuildError('Kein prüfbarer offizieller 7-Zip-Download verfügbar. System-7-Zip installieren oder ZIP/entpackten Ordner verwenden.')
        asset=assets[0]; archive=folder/'7z2603-x64.msi'
        expected=asset['digest'].split(':')[1]
        if archive.exists() and digest(archive)!=expected: raise BuildError('7-Zip-Download lokal verändert.')
        if not archive.exists(): download(asset['browser_download_url'], archive, expected_sha256=expected, maximum=64*1024**2, log=log)
        unpack=folder/'extracted'; unpack.mkdir(exist_ok=True)
        log('Offizielles 7-Zip-MSI in den lokalen Werkzeugordner entpacken …')
        run_process(['msiexec.exe','/a',str(archive),'/qn','TARGETDIR='+str(unpack)],timeout=240,log=log)
        matches=[p for p in unpack.rglob('7z.exe') if p.is_file()]
        if len(matches)!=1: raise BuildError('7-Zip-Programm nach MSI-Extraktion nicht eindeutig gefunden.')
        exe=matches[0]; dll=exe.with_name('7z.dll')
        if not dll.is_file(): raise BuildError('7-Zip-Bibliothek fehlt.')
        receipt={'exe':str(exe),'exe_sha256':digest(exe),'dll_sha256':digest(dll),'archive_sha256':expected}
        jsonwrite(folder/'receipt.json',receipt)
        os.environ['TCS_LOCAL_7ZIP']=str(exe)
        return str(exe)
    def load_sevenzip(self):
        try: return self._load_sevenzip_receipt()
        except (OSError,ValueError,KeyError,TypeError):
            os.environ.pop('TCS_LOCAL_7ZIP',None)
            return False
    def _load_sevenzip_receipt(self):
        receipt=self.root/'7zip'/'receipt.json'
        if receipt.exists():
            info=json.loads(receipt.read_text()); p=no_links(Path(info['exe']))
            if self.root not in p.parents or not p.is_file() or digest(p)!=info['exe_sha256']:
                return
            dll=p.with_name('7z.dll')
            if dll.is_file() and digest(dll)==info['dll_sha256']:
                os.environ['TCS_LOCAL_7ZIP']=str(p)
