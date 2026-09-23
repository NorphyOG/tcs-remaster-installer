"""Windows process checks independent of the console / ANSI code page.

Never interpret a failed check as "game not running". In v0.3 tasklist was
read with text=True; a decoding failure in a reader thread could leave stdout
as None. No locale-dependent text decoding is used for executable matching.
"""
from __future__ import annotations
import os
import subprocess
from safety import BuildError


def parse_tasklist(stdout: bytes | str | None, returncode: int, executable: str) -> bool:
    if returncode != 0:
        raise BuildError('Windows konnte die laufenden Programme nicht prüfen. Spiel schließen und erneut versuchen. Fehlercode: '+str(returncode))
    if isinstance(stdout, str):
        # Some process adapters return Unicode. Executable names here are ASCII.
        stdout = stdout.encode('utf-8', errors='replace')
    if not isinstance(stdout, bytes) or not stdout.strip():
        raise BuildError('Windows hat keine Prozessliste geliefert. Die Installation bleibt aus Sicherheitsgründen pausiert. Erneut versuchen; bei Wiederholung Diagnose speichern.')
    needle = executable.encode('ascii').lower()
    # tasklist /FO CSV includes the full executable name as its first field.
    # A localized "no tasks" message contains no matching quoted executable.
    return any(line.strip().lower().startswith(b'"'+needle+b'",') for line in stdout.splitlines())


def game_running(executable: str = 'LEGOStarWarsSaga.exe') -> bool:
    if os.name != 'nt':
        return False
    root = os.environ.get('SystemRoot', r'C:\Windows')
    tasklist = os.path.join(root, 'System32', 'tasklist.exe')
    try:
        result = subprocess.run(
            [tasklist, '/FI', f'IMAGENAME eq {executable}', '/FO', 'CSV', '/NH'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=20, shell=False, creationflags=0x08000000,
        )
    except subprocess.TimeoutExpired:
        raise BuildError('Windows-Prozessprüfung dauerte zu lange. Es wurden keine Dateien installiert. Bitte erneut versuchen.') from None
    except OSError:
        raise BuildError('Windows-Prozessprüfung konnte nicht gestartet werden. tasklist.exe bzw. Windows-Sicherheit prüfen; kein Spielordner wird verändert.') from None
    return parse_tasklist(result.stdout, result.returncode, executable)
