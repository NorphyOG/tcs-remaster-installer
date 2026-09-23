"""Path and archive safety; intentionally no code execution from mod packages."""
from __future__ import annotations
import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MAX_FILES = 160_000
MAX_BYTES = 24 * 1024**3
MAX_ARCHIVE = 8 * 1024**3
ANCHORS = {'chars', 'stuff', 'levels', 'audio', 'movies', 'music', 'sfx', 'textures', 'animations', 'effects', 'gui', 'shaders', 'fonts', 'text'}
BLOCKED = {'.exe','.dll','.com','.cmd','.bat','.ps1','.vbs','.vbe','.js','.jse','.msi','.scr','.lnk','.url','.py','.pyd','.asi','.reg','.sys','.hta','.jar','.sh','.so','.dylib','.msp','.cpl'}
RESERVED = re.compile(r'^(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?$', re.I)
class BuildError(ValueError):
    """A user-correctable, fail-closed validation error."""

def safe_rel(value: str) -> str:
    if not isinstance(value,str): raise BuildError('Ein Dateipfad fehlt oder ist nicht als Text angegeben.')
    name = value.replace('\\','/')
    if not name or name.startswith('/') or '\x00' in name or len(name) > 220:
        raise BuildError(f'Ungültiger oder zu langer relativer Pfad: {value!r}')
    parts = name.rstrip('/').split('/')
    for p in parts:
        if not p or p in {'.','..'} or p.endswith(('.',' ')) or RESERVED.match(p) or any(ord(c)<32 or c in ':<>"|?*' for c in p):
            raise BuildError(f'Unsicherer Windows-Pfad: {value!r}')
    return '/'.join(parts)

def linked(p: Path) -> bool:
    try:
        return p.is_symlink() or bool(p.lstat().st_file_attributes & 0x400)
    except AttributeError:
        return p.is_symlink()
    except FileNotFoundError:
        return False

def no_links(p: Path) -> Path:
    p = p.expanduser().absolute()
    for part in [p, *p.parents]:
        if linked(part):
            raise BuildError(f'Verknüpfung/Junction wird nicht als Dateiziel verwendet: {part}')
    return p

def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def bytehash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def find_7zip() -> str | None:
    local = os.environ.get('TCS_LOCAL_7ZIP')
    if local:
        p = no_links(Path(local))
        if p.is_file(): return str(p)
    if os.name == 'nt':
        for env in ('ProgramFiles','ProgramFiles(x86)'):
            p=Path(os.environ.get(env, 'C:/Program Files'))/'7-Zip'/'7z.exe'
            if p.is_file() and not linked(p): return str(p)
        return None
    return shutil.which('7zz') or shutil.which('7z')

def checked_entries(names: list[str]) -> None:
    lowered=[safe_rel(n).casefold() for n in names]
    if len(lowered)!=len(set(lowered)): raise BuildError('Doppelte Dateinamen oder Kollision bei Groß-/Kleinschreibung im Archiv.')
    files=set(lowered)
    for name in lowered:
        parts=name.split('/')
        if any('/'.join(parts[:i]) in files for i in range(1,len(parts))):
            raise BuildError('Eine Datei kollidiert mit einem Verzeichnis im Archiv.')

def unpack_external(path: Path, workspace: Path, log=lambda _:None) -> Path:
    """7-Zip is optional. Validate the full listing before extraction into isolation."""
    from diagnostics import check_cancel, phase
    check_cancel(log)
    phase(log,'unpack_mod','Modarchiv auflisten und isoliert entpacken …')
    tool=find_7zip()
    if not tool: raise BuildError('Dieses Archiv braucht 7-Zip. Im Download-Schritt 7-Zip installieren oder einen bereits entpackten Ordner hinzufügen.')
    run=lambda args, timeout: subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, creationflags=0x08000000 if os.name=='nt' else 0)
    try:
        result=run([tool,'l','-slt','-ba','-sccUTF-8','-pTCS-No-Encrypted-Archives','--',str(path)],180)
    except subprocess.TimeoutExpired as e:
        raise BuildError('Archivprüfung hat das Zeitlimit überschritten.') from e
    if result.returncode or not isinstance(result.stdout,bytes) or len(result.stdout)>80*1024**2:
        raise BuildError('7-Zip kann dieses Archiv nicht sicher auflisten. Verschlüsselte/mehrteilige Archive sind nicht vorgesehen.')
    rows=[]; row={}
    for line in result.stdout.decode('utf-8',errors='strict').splitlines()+['']:
        if not line:
            if row: rows.append(row); row={}
        elif ' = ' in line:
            k,v=line.split(' = ',1); row[k]=v
    names=[]; expected={}; total=0
    for row in rows:
        if 'Path' not in row: continue
        canonical=safe_rel(row['Path'])
        if row.get('Encrypted')=='+' or any(row.get(k) for k in ('Symbolic Link','Hard Link','Reparse Point')):
            raise BuildError('Verschlüsselte Dateien oder Links im Archiv sind nicht erlaubt.')
        attrs=row.get('Attributes','')
        if 'l' in attrs.split(' ')[-1][:1]: raise BuildError('Archiv enthält einen Link.')
        mode=attrs.split()[-1] if attrs.split() else ''
        if row.get('Folder')=='+' or attrs.startswith('D') or mode.startswith('d'): continue
        if 'Size' not in row: raise BuildError('Archiv enthält nicht prüfbare Größenangaben.')
        try: entry_size=int(row['Size'])
        except (ValueError, TypeError): raise BuildError('Archiv enthält ungültige Größenangaben.') from None
        if entry_size<0 or entry_size>MAX_BYTES: raise BuildError('Archiv enthält ungültige Größenangaben.')
        # Windows 7-Zip emits backslashes; pathlib emits forward slashes. Use
        # the SAME validated representation on both sides, never raw strings.
        names.append(canonical); expected[canonical.casefold()]=entry_size; total+=entry_size
    if not names or len(names)>MAX_FILES or total>MAX_BYTES: raise BuildError('Archiv ist leer oder überschreitet die Sicherheitsgrenzen.')
    checked_entries(names)
    if shutil.disk_usage(workspace).free < total+256*1024**2: raise BuildError('Zu wenig Speicher zum Entpacken.')
    if os.name == 'nt':
        # Python's mkdtemp creates a private Windows DACL that a 7-Zip
        # subprocess cannot always traverse under a restricted token.
        # Inherit the protected workspace ACL instead.
        out=no_links(workspace)/f'unpacked-{uuid.uuid4().hex}'
        out.mkdir()
    else:
        out=Path(tempfile.mkdtemp(prefix='unpacked-', dir=workspace))
    try:
        check_cancel(log)
        log('Geprüfte Moddateien werden entpackt. Das Spiel bleibt dabei unverändert.')
        result=run([tool,'x','-y','-bd','-bso0','-bsp0','-sccUTF-8','-pTCS-No-Encrypted-Archives',f'-o{out}','--',str(path)],1200)
        if result.returncode: raise BuildError('7-Zip hat einen Fehler gemeldet; die Ausgabe wird nicht verwendet.')
        # Re-scan without following symlinks, check actual paths and byte count.
        actual=[]; actual_sizes={}; size=0
        for root,dirs,files in os.walk(out, followlinks=False):
            check_cancel(log)
            for name in dirs+files:
                if linked(Path(root)/name): raise BuildError('Entpacktes Archiv enthält einen Link.')
            for name in files:
                p=Path(root)/name
                if not stat.S_ISREG(p.stat().st_mode): raise BuildError('Entpacktes Archiv enthält eine Spezialdatei.')
                rel=safe_rel(p.relative_to(out).as_posix()); entry_size=p.stat().st_size
                actual.append(rel); actual_sizes[rel.casefold()]=entry_size; size+=entry_size
                if len(actual)>MAX_FILES or size>MAX_BYTES: raise BuildError('Entpackte Ausgabe überschreitet die Sicherheitsgrenze.')
        checked_entries(actual)
        if actual_sizes!=expected or size!=total:
            missing=sorted(set(expected)-set(actual_sizes))
            extra=sorted(set(actual_sizes)-set(expected))
            changed=sorted(k for k in set(expected)&set(actual_sizes) if expected[k]!=actual_sizes[k])
            summary={'expected_files':len(expected),'actual_files':len(actual_sizes),
                     'expected_bytes':total,'actual_bytes':size,'missing':missing[:8],
                     'unexpected':extra[:8],'size_mismatch':changed[:8]}
            import json
            log('Archivvergleich: '+json.dumps(summary,ensure_ascii=False))
            raise BuildError('ARCHIVE_MISMATCH: Archivinhalt weicht von der geprüften Liste ab: '
                             f'{len(missing)} fehlen, {len(extra)} unerwartet, {len(changed)} falsche Größen. '
                             'Originalarchiv unverändert lassen; Diagnose speichern. Keine Dateien installiert.')
        log(f'Archivvergleich bestanden: {len(expected)} Dateien, jede Pfadangabe und Dateigröße stimmt überein.')
        return out
    except Exception:
        shutil.rmtree(out,ignore_errors=True)
        raise

@dataclass(frozen=True)
class Entry:
    name: str
    size: int
    original: str

class Source:
    def __init__(self,path: str|Path):
        self.path=no_links(Path(path)); self.archive=None; self.entries=[]
        if not self.path.exists(): raise BuildError(f'Quelle fehlt: {self.path}')
        try:
            if self.path.is_dir():
                total_size=0
                def walk_error(error):
                    raise BuildError('Mod-Quellordner kann nicht gelesen werden. Archiv erneut prüfen.') from error
                for root,dirs,files in os.walk(self.path,followlinks=False,onerror=walk_error):
                    for n in dirs+files:
                        if linked(Path(root)/n): raise BuildError('Verknüpfung im Quellordner ist nicht erlaubt.')
                    for n in files:
                        p=Path(root)/n
                        if not stat.S_ISREG(p.stat().st_mode): raise BuildError('Quelle enthält keine reguläre Datei.')
                        size=p.stat().st_size; total_size+=size
                        self.entries.append(Entry(safe_rel(p.relative_to(self.path).as_posix()),size,str(p)))
                        if len(self.entries)>MAX_FILES or total_size>MAX_BYTES: raise BuildError('Quellordner zu groß.')
            elif zipfile.is_zipfile(self.path):
                if self.path.stat().st_size>MAX_ARCHIVE: raise BuildError('Archiv größer als 8 GiB.')
                self.archive=zipfile.ZipFile(self.path)
                if len(self.archive.infolist())>MAX_FILES*2: raise BuildError('Zu viele Archiveinträge.')
                for info in self.archive.infolist():
                    safe_rel(info.filename)
                    mode=info.external_attr >> 16
                    if stat.S_ISLNK(mode) or (mode & 0o170000) not in (0,stat.S_IFREG,stat.S_IFDIR): raise BuildError('ZIP enthält Links oder Spezialdateien.')
                    if info.flag_bits & 1: raise BuildError('Verschlüsselte ZIPs sind nicht unterstützt.')
                    if not info.is_dir(): self.entries.append(Entry(safe_rel(info.filename),info.file_size,info.filename))
            else: raise BuildError('Bitte ZIP, 7z, RAR oder entpackten Modordner hinzufügen.')
            self._limit(); checked_entries([e.name for e in self.entries])
        except Exception:
            self.close(); raise
    def _limit(self):
        if len(self.entries)>MAX_FILES or sum(e.size for e in self.entries)>MAX_BYTES: raise BuildError('Quelle übersteigt 160.000 Dateien oder 24 GiB.')
    def close(self):
        if self.archive: self.archive.close(); self.archive=None
    def __enter__(self): return self
    def __exit__(self,*args): self.close()
    def roots(self) -> list[str]:
        result=set()
        for e in self.entries:
            parts=e.name.split('/')
            for i,p in enumerate(parts[:-1]):
                if p.casefold() in ANCHORS:
                    result.add('/'.join(parts[:i])); break
        return sorted(result,key=lambda x:(len(x.split('/')),x.casefold()))
    def selected(self,root: str) -> list[tuple[str,Entry]]:
        if root not in self.roots(): raise BuildError('Der gewählte Unterordner enthält keine bekannten TCS-Datenordner.')
        prefix=root+'/' if root else ''; result=[]
        for e in self.entries:
            if not e.name.startswith(prefix): continue
            rel=e.name[len(prefix):]
            # Include only immediate game-data anchors. Alternative sibling modules never leak in.
            if '/' not in rel or rel.split('/')[0].casefold() not in ANCHORS: continue
            if PurePosixPath(rel).suffix.casefold() in BLOCKED: raise BuildError(f'Ausführbare Datei im Datenmod: {rel}. Diese wird nicht installiert.')
            result.append((safe_rel(rel),e))
        if not result: raise BuildError('Der gewählte Daten-Unterordner ist leer.')
        return result
    def copy(self,e: Entry,target: Path) -> str:
        target.parent.mkdir(parents=True,exist_ok=True); h=hashlib.sha256(); count=0
        src=self.archive.open(e.original) if self.archive else no_links(Path(e.original)).open('rb')
        with src, target.open('wb') as dst:
            for b in iter(lambda:src.read(1024*1024), b''):
                count+=len(b)
                if count>e.size: raise BuildError('Quelldatei wurde während des Lesens verändert.')
                h.update(b); dst.write(b)
        if count!=e.size: raise BuildError('Quelldatei unvollständig.')
        return h.hexdigest()
