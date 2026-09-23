"""Bounded reader for the TT PAK 0x1234567a table (not a generic .pak guess).

Format references, checked 2026-09-23:
- linterniGamer/Tt-Games-quickbms-scripts/files/ttgames.bms,
  EXTRACT_1234567a and DEFLATE_UNPACK.
- AcK77/TTGames-Explorer-Rebirth/src/TTGamesExplorerRebirthLib/Formats/PAK.cs.

Own implementation; no game data or upstream code is bundled. Raw entries are
copied exactly. Compressed entries still use the existing QuickBMS DFLT codec,
with a narrowly matched, bounded look-ahead patch. No error exit is accepted.
"""
from __future__ import annotations
import hashlib
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from diagnostics import check_cancel, progress
from safety import BLOCKED, MAX_BYTES, MAX_FILES, BuildError, checked_entries, digest, no_links, safe_rel

MAGIC = b'\x7a\x56\x34\x12'
POLICY = 'tt-pak-bounded-v1'
HEADER = struct.Struct('<6I')
RECORD = struct.Struct('<7I')
COPY_BLOCK = 1024 * 1024


@dataclass(frozen=True)
class PakEntry:
    path: str
    offset: int
    stored_bytes: int
    output_bytes: int
    compressed: bool

    @property
    def excluded(self) -> bool:
        return Path(self.path).suffix.lower() in BLOCKED


@dataclass(frozen=True)
class PakIndex:
    archive: Path
    sha256: str
    actual_bytes: int
    header_size_field: int
    entries: tuple[PakEntry, ...]

    def listing(self) -> dict:
        return {r.path.casefold(): {'path': r.path, 'bytes': r.output_bytes}
                for r in self.entries if not r.excluded}

    def exclusions(self) -> list:
        return [{'path': r.path, 'bytes': r.output_bytes, 'reason': 'runtime-or-script',
                 'action': 'not-extracted'} for r in self.entries if r.excluded]

    @property
    def needs_codec(self) -> bool:
        return any(r.compressed and not r.excluded for r in self.entries)

    def summary(self, method: str) -> dict:
        return {'policy': POLICY, 'method': method, 'entries': len(self.entries),
                'short_entries': sum(r.stored_bytes < 32 for r in self.entries),
                'zero_entries': sum(r.stored_bytes == 0 for r in self.entries),
                'compressed_entries': sum(r.compressed for r in self.entries),
                'archive_bytes': self.actual_bytes,
                'header_size_field': self.header_size_field,
                'archive_sha256': self.sha256,
                'checksum_field_verified': False}


def _exact(stream, size: int, label: str) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise BuildError('PAK-Daten abgeschnitten: ' + label + '. Keine Spieländerung.')
    return data


def inspect_pak(archive: Path, log=lambda _: None) -> PakIndex | None:
    """Unknown magic -> caller's normal parser; known, invalid PAK -> hard stop.

    Names, ranges and output sizes are validated before any extraction. Never
    look beyond an entry to guess its compression, even when other bytes follow.
    Unknown flags/checksum semantics are retained, not presented as verified.
    """
    archive = no_links(archive)
    with archive.open('rb') as f:
        if f.read(4) != MAGIC:
            return None
        f.seek(0)
        _, count, size_field, _checksum, _unknown, _reserved = HEADER.unpack(
            _exact(f, HEADER.size, 'Header'))
        actual = archive.stat().st_size
        table_end = HEADER.size + count * RECORD.size
        if count > MAX_FILES or actual > MAX_BYTES or table_end > actual:
            raise BuildError('PAK-Dateitabelle fehlt oder überschreitet die Grenzen: ' + archive.name)
        rows = []; total = 0
        for n in range(count):
            check_cancel(log)
            f.seek(HEADER.size + n * RECORD.size)
            name_offset, offset, stored, _flag, _zero, _hash1, _hash2 = RECORD.unpack(
                _exact(f, RECORD.size, 'Dateitabelle'))
            if not table_end <= name_offset < actual:
                raise BuildError(f'PAK-Namensoffset außerhalb des Namens-/Datenbereichs (Eintrag {n+1}).')
            if not table_end <= offset <= actual or stored > actual - offset:
                raise BuildError(f'PAK-Dateibereich außerhalb des Archivs (Eintrag {n+1}). Archiv nicht vollständig oder Format unbekannt.')
            f.seek(name_offset)
            name_bytes = f.read(min(222, actual - name_offset))
            end = name_bytes.find(b'\0')
            if end < 0:
                raise BuildError('PAK-Dateiname nicht abgeschlossen oder zu lang.')
            try:
                name = name_bytes[:end].decode('ascii', errors='strict')
            except UnicodeDecodeError:
                raise BuildError('PAK-Dateiname hat eine nicht bestätigte Zeichenkodierung. Kein geratener Zielpfad.') from None
            rel = safe_rel(name)
            if any(p.startswith('.') for p in rel.split('/')):
                raise BuildError('Administrativer Pfad im PAK: ' + rel)
            f.seek(offset)
            # The 0.3.2 bug: an unconditional read(32) here also reads past EOF.
            probe = _exact(f, min(stored, 32), rel)
            compressed = probe.split(b'\0', 1)[0] == b'Deflate_v1.0'
            output = stored
            if compressed:
                if stored < 36:
                    raise BuildError('Unvollständiger Deflate_v1.0-Header: ' + rel)
                output = struct.unpack('<I', _exact(f, 4, rel + ' Größenfeld'))[0]
                if stored == 36 and output:
                    raise BuildError('Komprimierte PAK-Nutzdaten fehlen: ' + rel)
            total += output
            if total > MAX_BYTES:
                raise BuildError('PAK-Ausgabe überschreitet das Extraktionslimit.')
            rows.append(PakEntry(rel, offset, stored, output, compressed))
        checked_entries([r.path for r in rows])
    check_cancel(log)
    return PakIndex(archive, digest(archive), actual, size_field, tuple(rows))


def extract_raw(index: PakIndex, folder: Path, log=lambda _: None) -> None:
    """Only raw entries. No content execution, no padding, no missing-file skip."""
    if index.needs_codec:
        raise BuildError('Komprimierte PAK-Dateien benötigen den geprüften Codec.')
    if digest(index.archive) != index.sha256:
        raise BuildError('PAK wurde zwischen Prüfung und Extraktion verändert.')
    with no_links(index.archive).open('rb') as f:
        for i, row in enumerate(index.entries):
            check_cancel(log)
            if row.excluded:
                continue
            target = no_links(folder / safe_rel(row.path))
            target.parent.mkdir(parents=True, exist_ok=True)
            f.seek(row.offset)
            with target.open('xb') as out:
                left = row.stored_bytes
                while left:
                    check_cancel(log)
                    data = _exact(f, min(COPY_BLOCK, left), row.path)
                    out.write(data); left -= len(data)
            progress(log, i + 1, len(index.entries))
    if digest(index.archive) != index.sha256:
        raise BuildError('PAK während der Extraktion verändert. Keine Übernahme.')


def patched_deflate_script(source: Path, destination: Path) -> dict:
    """Patch only the exact known routine, never arbitrary downloaded code.

    The original script and its receipt remain untouched. This derivative lives
    outside the payload folder. Unrecognised scripts fail closed.
    """
    text = no_links(source).read_text(encoding='utf-8-sig')
    pattern = re.compile(r'^startfunction DEFLATE_UNPACK\s*\n.*?^endfunction\b', re.M | re.S)
    matches = list(pattern.finditer(text))
    expected = ('startfunction DEFLATE_UNPACK getdstring SIGN 0x20 '
                'if SIGN == "Deflate_v1.0" comtype dflt get XSIZE long '
                'math OFFSET + 0x24 math SIZE - 0x24 clog NAME OFFSET SIZE XSIZE '
                'else log NAME OFFSET SIZE endif endfunction')
    if len(matches) != 1 or ' '.join(matches[0].group().split()) != expected:
        raise BuildError('Die PAK-Signaturfunktion im TT-Skript ist unbekannt. Keine automatische Skriptänderung.')
    replacement = '''startfunction DEFLATE_UNPACK
    # TCS installer: entry-bounded signature probe; not an error-code bypass.
    math TCS_PROBE_SIZE = SIZE
    if TCS_PROBE_SIZE > 0x20
        math TCS_PROBE_SIZE = 0x20
    endif
    set SIGN string ""
    if TCS_PROBE_SIZE > 0
        getdstring SIGN TCS_PROBE_SIZE
    endif
    if SIGN == "Deflate_v1.0"
        if SIZE < 0x24
            print "Error: incomplete Deflate_v1.0 header"
            cleanexit
        endif
        comtype dflt
        get XSIZE long
        math OFFSET + 0x24
        math SIZE - 0x24
        clog NAME OFFSET SIZE XSIZE
    else
        log NAME OFFSET SIZE
    endif
endfunction'''
    match = matches[0]
    result = text[:match.start()] + replacement + text[match.end():]
    from nettools import validate_script
    validate_script(result)
    target = no_links(destination)
    target.write_text(result, encoding='utf-8')
    return {'source_sha256': digest(source), 'derived_sha256': digest(target),
            'patch': 'bounded-DEFLATE_UNPACK-v1'}
