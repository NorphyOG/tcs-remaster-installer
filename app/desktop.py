"""Own app-mode window using installed Edge/Chrome, with browser fallback.
No Electron, pip downloads or browser security flags disabled. Windows integration
must be tested on Windows; command building is covered by platform-neutral tests.
"""
from __future__ import annotations
import os
import re
import subprocess
import webbrowser
from pathlib import Path
from safety import no_links, BuildError


def window_command(browser:Path,url:str,base:Path):
    if not re.fullmatch(r'http://127\.0\.0\.1:[0-9]+/#[A-Za-z0-9_-]+',url):
        raise ValueError('Only our loopback session may open in the app window')
    return [str(browser), '--app='+url,
            '--user-data-dir='+str(base/'.local'/'window-profile'),
            '--no-first-run','--no-default-browser-check','--window-size=1380,940']


def find_browser():
    if os.name!='nt':return None
    for rel in ('Microsoft/Edge/Application/msedge.exe','Google/Chrome/Application/chrome.exe'):
        for env in ('ProgramFiles(x86)','ProgramFiles','LOCALAPPDATA'):
            value=os.environ.get(env)
            if not value:continue
            p=Path(value)/rel
            try:
                if no_links(p).is_file():return p
            except (ValueError,OSError,BuildError):pass
    return None


def open_window(url,base,*,browser_only=False):
    browser=None if browser_only else find_browser()
    if browser:
        try:
            subprocess.Popen(window_command(browser,url,Path(base)),shell=False,
                             creationflags=0x08000000 if os.name=='nt' else 0)
            return 'app-window'
        except OSError:pass
    webbrowser.open(url)
    return 'browser-fallback'
