"""Windows per-user shell integration and narrowly scoped UAC write worker.
No hidden takeover of Vortex's global nxm handler. All paths are literal arguments.
"""
from __future__ import annotations
import base64
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from engine import jsonwrite, describe_game
from safety import BuildError, no_links, digest
from nettools import require_windows


def _powershell_process(script: str, env: dict | None=None, timeout=120):
    require_windows()
    encoded=base64.b64encode(script.encode('utf-16le')).decode('ascii')
    return subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],
                          env={**os.environ,**(env or {})},capture_output=True,timeout=timeout,shell=False,creationflags=0x08000000)


def powershell(script: str, env: dict | None=None, timeout=120):
    run=_powershell_process(script,env,timeout)
    if run.returncode: raise BuildError('Windows hat diesen Schritt abgelehnt oder eine Bestätigung wurde abgebrochen.')
    return run.stdout.decode('utf-8-sig',errors='replace').strip()


def elevation_failure(run) -> BuildError:
    """Report only a bounded status marker, never arbitrary helper output."""
    marker=run.stdout.decode('utf-8-sig',errors='replace').strip()
    if marker=='launch-win32:1223':
        return BuildError('Windows hat die Administratorabfrage abgebrochen oder nicht angezeigt. Keine Moddatei wurde installiert.')
    if marker.startswith('launch-win32:') and marker[13:].isdigit():
        code=marker[13:]
        return BuildError('Windows konnte die Administratorabfrage nicht öffnen (Fehler '+code+'). '
                          'Assistent in der normalen Windows-Sitzung über STARTEN.cmd öffnen und erneut versuchen.')
    if marker.startswith('worker-exit:') and marker[12:].isdigit():
        return BuildError('Der Windows-Schreibprozess wurde mit Exitcode '+marker[12:]
                          +' beendet. Vor erneutem Installieren Spielordner und Sicherungsjournal prüfen; Diagnose speichern.')
    return BuildError('Windows konnte den Schreibprozess nicht starten (Exitcode '+str(run.returncode)+'). '
                      'Assistent in der normalen Windows-Sitzung über STARTEN.cmd öffnen und Diagnose speichern.')


def protocol_status():
    if os.name!='nt': return {'available':False,'registered':False,'handler':''}
    import winreg
    def value(hive,key,name=''):
        try:
            with winreg.OpenKey(hive,key) as k: return winreg.QueryValueEx(k,name)[0]
        except OSError: return ''
    ours=value(winreg.HKEY_CURRENT_USER,r'Software\Classes\nxm','TCSInstallerOwner')
    handler=value(winreg.HKEY_CLASSES_ROOT,r'nxm\shell\open\command')
    return {'available':True,'registered':bool(ours),'handler':handler,'owner':ours}


def register_nxm(base: Path, *, confirmation: str):
    require_windows()
    if confirmation!='REGISTER_NXM': raise BuildError('NXM-Zuordnung ausdrücklich bestätigen; sie gilt Windows-weit für diesen Benutzer.')
    import winreg
    backup=base/'.local'/'nxm-registry-backup.json'
    keypath=r'Software\Classes\nxm'
    def capture(path):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path) as k:
                vals=[]; i=0
                while True:
                    try:
                        name,value,kind=winreg.EnumValue(k,i); i+=1
                        if isinstance(value,bytes): value={'base64':base64.b64encode(value).decode('ascii')}
                        vals.append((name,value,kind))
                    except OSError: break
                children={}; i=0
                while True:
                    try: sub=winreg.EnumKey(k,i); i+=1; children[sub]=capture(path+'\\'+sub)
                    except OSError: break
                return {'values':vals,'children':children}
        except FileNotFoundError: return None
    if not backup.exists(): jsonwrite(backup,{'registry':capture(keypath),'owner':str(base)})
    else:
        old=json.loads(backup.read_text())
        if old['owner']!=str(base): raise BuildError('Registry-Backup gehört zu einem anderen Installer.')
    command=subprocess.list2cmdline([sys.executable,str(base/'app'/'nxm_handler.py')])+' "%1"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,keypath) as k:
        winreg.SetValueEx(k,'',0,winreg.REG_SZ,'URL:TCS Remaster Nexus Bridge')
        winreg.SetValueEx(k,'URL Protocol',0,winreg.REG_SZ,'')
        winreg.SetValueEx(k,'TCSInstallerOwner',0,winreg.REG_SZ,str(base))
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,keypath+r'\shell\open\command') as k:
        winreg.SetValueEx(k,'',0,winreg.REG_SZ,command)
    # Remove a stale DelegateExecute value, which would take priority over our command.
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,keypath+r'\shell\open\command',0,winreg.KEY_SET_VALUE) as k:
        try: winreg.DeleteValue(k,'DelegateExecute')
        except FileNotFoundError: pass
    return protocol_status()


def unregister_nxm(base: Path):
    require_windows()
    import winreg
    backup=base/'.local'/'nxm-registry-backup.json'
    if not backup.is_file(): raise BuildError('Keine von diesem Installer gesicherte NXM-Zuordnung vorhanden.')
    status=protocol_status()
    expected_command=subprocess.list2cmdline([sys.executable,str(base/'app'/'nxm_handler.py')])+' "%1"'
    if status.get('owner')!=str(base) or status.get('handler')!=expected_command:
        raise BuildError('Ein anderer Manager hat die NXM-Zuordnung inzwischen geändert. Keine Registry-Änderung.')
    keypath=r'Software\Classes\nxm'
    def remove(path):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,path,0,winreg.KEY_READ|winreg.KEY_WRITE) as k:
                children=[]; i=0
                while True:
                    try: children.append(winreg.EnumKey(k,i)); i+=1
                    except OSError: break
            for child in children: remove(path+'\\'+child)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER,path)
        except FileNotFoundError: pass
    def restore(path,data):
        if data is None:return
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,path) as k:
            for name,value,kind in data['values']:
                if isinstance(value,dict) and 'base64' in value: value=base64.b64decode(value['base64'])
                winreg.SetValueEx(k,name,0,kind,value)
        for child,sub in data['children'].items(): restore(path+'\\'+child,sub)
    data=json.loads(backup.read_text()); remove(keypath); restore(keypath,data['registry']); backup.unlink()
    return protocol_status()


def create_shortcuts(base: Path, game_path: str, *, desktop=True):
    require_windows(); info=describe_game(game_path)
    target=base/'.local'/'shortcuts'; target.mkdir(exist_ok=True)
    # A local guarded launcher verifies hashes and starts the selected game copy.
    script=r''' 
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$d = if ($env:TCS_DESKTOP -eq '1') { [Environment]::GetFolderPath('Desktop') } else { $env:TCS_SHORTCUT_DIR }
if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
$w = New-Object -ComObject WScript.Shell
foreach ($item in @(@('TCS Remaster - geprueft starten.lnk', $env:TCS_LAUNCHER), @('TCS Modpack verwalten.lnk', $env:TCS_SERVER))) {
  $p = Join-Path $d $item[0]
  if (-not (Test-Path -LiteralPath $p)) {
    $s=$w.CreateShortcut($p); $s.TargetPath=$env:TCS_PYTHON
    $s.Arguments='"'+$item[1]+'"'; $s.WorkingDirectory=$env:TCS_BASE
    $s.IconLocation=$env:TCS_ICON; $s.Description='TCS Remaster: lokaler Installer / gepruefter Spielstart'
    $s.Save()
  }
}
[Console]::Write((Join-Path $d 'TCS Remaster - geprueft starten.lnk'))
'''
    path=powershell(script,{'TCS_DESKTOP':'1' if desktop else '0','TCS_SHORTCUT_DIR':str(target),
        'TCS_PYTHON':sys.executable,'TCS_SERVER':str(base/'app'/'server.py'),
        'TCS_LAUNCHER':str(base/'app'/'readiness.py'),'TCS_ICON':str(base/'web'/'icon.ico'),'TCS_BASE':str(base)})
    return {'shortcut':path,'launch':'verified_selected_original_executable','game_tested':False}


def elevated_action(base: Path, action: str, payload: dict):
    """Only offline file actions run elevated; the web/API/downloader stays unelevated."""
    require_windows()
    if action not in ('prepare_commit','prepare_restore','install','restore'): raise BuildError('Unzulässiger Windows-Schreibauftrag.')
    folder=base/'.local'/'elevated'; folder.mkdir(exist_ok=True)
    request=folder/(uuid.uuid4().hex+'.json'); result=request.with_suffix('.result.json')
    jsonwrite(request,{'action':action,'payload':payload,'result':str(result)})
    checksum=digest(request)
    args=subprocess.list2cmdline([str(base/'app'/'elevated_worker.py'),str(request),checksum])
    script=r'''
$psi=New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName=$env:TCS_ELEVATE_PYTHON
$psi.Arguments=$env:TCS_ELEVATE_ARGS
$psi.WorkingDirectory=$env:TCS_ELEVATE_BASE
$psi.Verb='runas'; $psi.UseShellExecute=$true
try {
  $p=[System.Diagnostics.Process]::Start($psi)
  if ($null -eq $p) { [Console]::WriteLine('launch-null'); exit 1 }
  $p.WaitForExit()
  if ($p.ExitCode -ne 0) { [Console]::WriteLine('worker-exit:'+$p.ExitCode); exit 1 }
} catch {
  $cause=$_.Exception
  while ($null -ne $cause.InnerException) { $cause=$cause.InnerException }
  if ($cause -is [System.ComponentModel.Win32Exception]) {
    [Console]::WriteLine('launch-win32:'+$cause.NativeErrorCode)
  } else {
    [Console]::WriteLine('launch-exception:'+$cause.GetType().Name)
  }
  exit 1
}
'''
    try:
        run=_powershell_process(script,{'TCS_ELEVATE_PYTHON':sys.executable,'TCS_ELEVATE_ARGS':args,'TCS_ELEVATE_BASE':str(base)},timeout=7200)
        if run.returncode: raise elevation_failure(run)
        if not result.is_file(): raise BuildError('Windows-Schreibauftrag hat kein Ergebnis zurückgeliefert.')
        output=json.loads(result.read_text(encoding='utf-8'))
        if output.get('error'): raise BuildError(output['error'])
        return output['result']
    finally:
        request.unlink(missing_ok=True)
        result.unlink(missing_ok=True)
