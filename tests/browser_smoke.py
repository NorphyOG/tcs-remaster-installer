"""Real Chromium smoke test with unmistakably synthetic data. Not a game test.
Developer-only dependency: Playwright + Chromium. End users do not need either.
"""
from __future__ import annotations
import json
import base64
import http.client
import re
import os
import shutil
import sys
import threading
import time
import zipfile
from pathlib import Path
from helpers import Fixture, BASE
from server import make_server
from safety import BuildError
from unittest.mock import patch
from playwright.sync_api import sync_playwright, Error


def local_bridge(page, server, base):
    """Test-only adapter for sandboxes whose Chromium policy blocks ALL URLs.
    Does not alter browser/system policy. Renders in about:blank and bridges
    only our own /api requests to our ephemeral localhost HTTP server.
    Browser navigation/session bootstrap and OS downloads are NOT tested here.
    """
    port=server.server_address[1]
    def request(req):
        path=req['path']
        if not path.startswith('/api/') or '\\' in path or '..' in path:
            raise ValueError('Only this test server API is permitted')
        headers=dict(req.get('headers',{})); headers['Origin']=server.app.origin
        connection=http.client.HTTPConnection('127.0.0.1',port,timeout=90)
        body=base64.b64decode(req.get('body',''))
        connection.request(req.get('method','GET'),path,body=body,headers=headers)
        response=connection.getresponse(); data=response.read()
        result={'status':response.status,'headers':dict(response.getheaders()),'body':base64.b64encode(data).decode()}
        connection.close(); return result
    page.expose_function('__local_test_request',request)
    html=(base/'web/index.html').read_text(encoding='utf-8')
    html=re.sub(r'<link[^>]*rel="stylesheet"[^>]*>', '', html)
    html=re.sub(r'<script[^>]*src="(?:app|auto|journey).js"[^>]*></script>', '', html)
    html=html.replace('src="icon.svg"','src="data:image/svg+xml;base64,'+base64.b64encode((base/'web/icon.svg').read_bytes()).decode()+'"')
    page.set_content(html)
    page.add_style_tag(content=(base/'web/style.css').read_text(encoding='utf-8'))
    page.evaluate("""() => {
      window.__testDownloads=[];
      const click=HTMLAnchorElement.prototype.click;
      HTMLAnchorElement.prototype.click=function(){
        if(this.download && this.href.startsWith('blob:')) {window.__testDownloads.push(this.download);return;}
        return click.call(this);
      };
      window.fetch=async(path,options={})=>{
        if(typeof path!=='string'||!path.startsWith('/api/')) throw Error('Test adapter only permits local API');
        let bytes=new Uint8Array();
        if(options.body instanceof Blob) bytes=new Uint8Array(await options.body.arrayBuffer());
        else if(options.body) bytes=new TextEncoder().encode(options.body);
        let binary='';for(const b of bytes) binary+=String.fromCharCode(b);
        const r=await window.__local_test_request({path,method:options.method||'GET',headers:options.headers||{},body:btoa(binary)});
        const raw=atob(r.body);const output=Uint8Array.from(raw,c=>c.charCodeAt(0));
        return new Response(output,{status:r.status,headers:r.headers});
      };
    }""")
    script=(base/'web/app.js').read_text(encoding='utf-8')
    first=script.index('let token=');last=script.index('let app=',first)
    script=script[:first]+'let token='+json.dumps(server.app.token)+';\n'+script[last:]
    page.add_script_tag(content=script)
    page.add_script_tag(content=(base/'web/auto.js').read_text(encoding='utf-8'))
    page.add_script_tag(content=(base/'web/journey.js').read_text(encoding='utf-8'))


def wait_download(page, selector, bridge):
    if bridge:
        old=page.evaluate('window.__testDownloads.length')
        page.click(selector)
        page.wait_for_function('(n)=>window.__testDownloads.length>n',arg=old,timeout=60000)
        return page.evaluate('window.__testDownloads.at(-1)')
    with page.expect_download() as download_info:page.click(selector)
    return download_info.value.suggested_filename


def main():
    f=Fixture(); server=make_server(0,f.base); thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    output=Path(os.environ.get('TCS_SCREENSHOT_DIR',str(BASE/'docs')));output.mkdir(parents=True,exist_ok=True)
    class Checks(list):
        def append(self,value):
            super().append(value); print('PASS',value,flush=True)
    artifacts=[]; checks=Checks()
    (f.game/'CHARS'/'chars.txt').write_bytes(b'boba=1\njedi=2\nvehicle=3\n')
    payloads=[
        ('Lego Star Wars The Complete Saga Modern Overhaul - DEMO Testdaten.zip',{
            'Main/CHARS/Boba/Body.gsc':b'\x00model-A',
            'Main/CHARS/chars.txt':b'boba=10\njedi=2\nvehicle=3\n',
            'Main/STUFF/environment.txt':b'illustrative only'}),
        ('Additional Levels Modern Overhaul - DEMO Testdaten.zip',{
            'Main/CHARS/chars.txt':b'boba=1\njedi=2\nvehicle=30\n',
            'Main/LEVELS/Bonus/test.txt':b'not a real level'}),
        ('Refinement Overhaul - DEMO Testdaten.zip',{
            'Common/CHARS/Boba/Body.gsc':b'\x00model-B',
            'Classic Icons/STUFF/ICONS_PC.GSC':b'\x00classic-icons',
            'MO Icons/STUFF/ICONS_PC.GSC':b'\x00excluded-alternative'}),
        ('Compatibility Patches Additional Levels - DEMO Testdaten.zip',{
            'Common Patch/CHARS/Bonus/test.txt':b'not a real character',
            'Classic Icons/STUFF/ICONS_PC.GSC':b'\x00classic-patch',
            'MO Icons/STUFF/ICONS_PC.GSC':b'\x00excluded-alternative'})]
    archives=[]
    for name,files in payloads:
        p=f.root/name
        with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
            for rel,data in files.items():z.writestr(rel,data)
        archives.append(str(p))
    errors=[]
    try:
        with sync_playwright() as pw:
            executable=shutil.which('chromium') or shutil.which('google-chrome')
            browser=pw.chromium.launch(headless=True,executable_path=executable,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1120},device_scale_factor=1)
            page.on('pageerror',lambda e:errors.append(str(e)))
            bridge=bool(os.environ.get('TCS_FORCE_BRIDGE'))
            if bridge:
                local_bridge(page,server,f.base)
            else:
                try:page.goto(server.app.origin+'/#'+server.app.token,timeout=10000)
                except Error as exc:
                    if 'ERR_BLOCKED_BY_ADMINISTRATOR' not in str(exc):raise
                    bridge=True
                    page.close();page=browser.new_page(viewport={'width':1440,'height':1120},device_scale_factor=1)
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    local_bridge(page,server,f.base)
            page.wait_for_function("document.querySelector('#runtimeBadge').textContent.includes('Lokal verbunden')")
            checks.append('Wizard rendered in Chromium; local API authenticated'+(' through test-only transport adapter' if bridge else ''))
            page.fill('#gamePath',str(f.root/'wrong-game'));page.click('#checkGameBtn');page.wait_for_selector('#toast:not([hidden])')
            page.fill('#gamePath',str(f.game));page.click('#checkGameBtn');page.wait_for_selector('#gameStatus .notice.good')
            assert page.locator('#toast').is_hidden()
            checks.append('Stale EXE-not-found toast clears after successful game-folder check')
            assert page.locator('#prepareBtn').is_visible() and page.locator('#autoStartBtn').is_visible()
            assert not page.locator('#allowTools').is_checked()
            checks.append('Automatic preparation visible; external tool download still requires consent')
            page.evaluate("()=>{const d=document.createElement('div');d.id='demoLabel';d.textContent='UI-PREVIEW · künstliche Testinstallation · kein Windows-Spieltest';d.style.cssText='position:fixed;right:20px;top:10px;z-index:100;background:#352443;color:#eee;padding:7px 12px;border-radius:8px;font:12px system-ui;';document.body.appendChild(d)}")
            page.screenshot(path=str(output/'04-automation.png'),full_page=True);artifacts.append('04-automation.png')
            page.check('#cleanTarget');assert page.locator('#prepared').is_checked() and page.locator('#prepared').is_disabled();page.locator('#baselineConfirmed').evaluate("e=>e.closest('details').open=true");page.check('#baselineConfirmed')
            checks.append('Game-path input and structural preflight worked')
            page.locator('nav [data-step="2"]').click()
            page.evaluate("""(()=>{document.getElementById('demoLabel')?.remove();const d=document.createElement('div');d.id='demoLabel';d.textContent='DEMO · künstliche Testdateien, keine echten Mods';d.style.cssText='position:fixed;right:20px;top:10px;z-index:100;background:#352443;border:1px solid #b18fc9;color:#eee;padding:7px 12px;border-radius:8px;font:12px system-ui;';document.body.appendChild(d);})()""")
            page.wait_for_function("document.querySelector('#auditTable').textContent.includes('Refinement Overhaul')")
            checks.append('Author-file audit rendered, including alternative Optional files')
            assert page.locator('#nexusAllBtn').is_disabled()
            checks.append('Premium download is disabled without connected premium account')
            assert page.locator('#nexusKey').get_attribute('type')=='password'
            checks.append('Nexus key input masked; no prefilled account credential')
            assert page.locator('#journeyStages .stage-card').count()==7
            checks.append('Seven separate stage progress cards rendered')
            assert page.locator('[data-stage="install"] .stage-label').inner_text()=='Noch offen'
            checks.append('Prepared game does not imply installed mods')
            with patch('server.webbrowser.open') as opened:
                page.click('#nextDownloadBtn')
                page.wait_for_function("document.querySelector('#watchStatus').textContent.includes('Beobachtet:')")
                assert opened.call_count==1
                assert 'file_id=583' in opened.call_args.args[0]
            checks.append('Next missing download opens exact recipe file via backend; no network download simulated as successful')
            assert str(f.base/'mods') in page.locator('#watchStatus').inner_text()
            checks.append('Download helper enables selected folder plus local mods folder')
            page.screenshot(path=str(output/'01-downloads.png'),full_page=True);artifacts.append('01-downloads.png')
            # Upload through the actual browser file input, not just through a core API.
            page.set_input_files('#archiveInput',archives)
            page.wait_for_function("document.querySelector('#archiveStatus').textContent.startsWith('4 ')",timeout=60000)
            page.wait_for_function("!document.body.classList.contains('busy')",timeout=60000)
            checks.append('Four synthetic ZIPs uploaded, imported and heuristically mapped via the browser')
            page.locator('nav [data-step="3"]').click()
            for mid in ('modern-overhaul','additional-levels-mo','infinities','infinities-al-patch'):
                page.check(f'[data-confirm="{mid}"]')
            inf_roots=page.locator('[data-root-module="infinities"]:checked').evaluate_all('(els)=>els.map(e=>e.dataset.root)')
            assert 'Common' in inf_roots and 'Classic Icons' in inf_roots and 'MO Icons' not in inf_roots, inf_roots
            checks.append('Common + Classic chosen; alternative MO icon folder excluded')
            page.evaluate('loadState(false,true)')
            assert all(page.locator(f'[data-confirm="{mid}"]').is_checked() for mid in ('modern-overhaul','additional-levels-mo','infinities','infinities-al-patch'))
            checks.append('Background refresh preserves unsaved module confirmations')
            page.locator('[data-module="infinities"]').scroll_into_view_if_needed()
            page.screenshot(path=str(output/'02-mapping.png'),full_page=False);artifacts.append('02-mapping.png')
            assert page.locator('[data-root-module=modern-overhaul]:checked').count()==1, page.evaluate('app.state.selections')
            page.click('#saveSelectionsBtn');page.click('#planBtn')
            page.wait_for_function("document.querySelector('#metrics .metric') || !document.querySelector('#toast').hidden",timeout=60000)
            assert 'automatisch geregelt' in page.locator('#planFreshness').inner_text(), (page.locator('#planFreshness').inner_text(),page.locator('#toastText').inner_text(),server.app.job)
            counts=page.locator('.metric strong').all_text_contents()
            assert counts[1]=='2' and counts[2]=='1' and counts[3]=='0',counts
            assert not page.locator('#toInstallBtn').is_disabled()
            assert page.locator('#resumeStepBtn').get_attribute('data-step')=='5'
            checks.append('Two known author overlays and one non-overlapping text merge resolved automatically')
            page.screenshot(path=str(output/'03-conflicts.png'),full_page=True);artifacts.append('03-conflicts.png')
            assert page.locator('#conflicts select').count()==0
            checks.append('Conflict screen does not request per-file variant choices')
            page.locator('.project-info summary').click()
            page.screenshot(path=str(output/'10-project-info.png'),full_page=False);artifacts.append('10-project-info.png')
            assert wait_download(page,'#downloadReportBtn',bridge)=='TCS-Pruefbericht.json'
            checks.append('Local JSON audit payload received; download action prepared')
            page.click('#toInstallBtn');page.click('#buildBtn')
            page.wait_for_selector('#installResult .panel',timeout=60000)
            assert 'Lokale Mod-ZIP erstellt' in page.locator('#installResult').inner_text()
            checks.append('Reloaded-compatible local mod ZIP built from synthetic sources')
            result=server.app.engine.state['last_build']
            with zipfile.ZipFile(result['archive']) as z:
                merged=z.read('Redirector/CHARS/chars.txt')
                assert b'boba=10' in merged and b'vehicle=30' in merged
                assert not any('MO Icons' in n for n in z.namelist())
            checks.append('Result ZIP inspected: combined text retained; rejected alternative excluded')
            page.locator('nav [data-step="6"]').click()
            assert wait_download(page,'#exportBtn',bridge).endswith('.zip')
            checks.append('Public installer export payload received; download action prepared')
            page.set_viewport_size({'width':390,'height':844});page.locator('nav [data-step="2"]').click()
            width=page.evaluate('({scroll:document.documentElement.scrollWidth,viewport:window.innerWidth})')
            assert width['scroll']<=width['viewport']+2,width
            checks.append('390px responsive layout has no horizontal page overflow')
            page.evaluate("window.scrollTo(0,document.body.scrollHeight)")
            assert page.locator('.sidebar').evaluate('e=>Math.round(e.getBoundingClientRect().top)')==0
            assert all(page.locator(f'nav [data-step="{n}"]').is_visible() for n in range(1,7))
            page.locator('nav [data-step="4"]').click()
            assert page.locator('#step4 h1').is_visible()
            page.evaluate("document.getElementById('demoLabel').style.cssText+='top:auto;bottom:10px;right:10px;'")
            page.screenshot(path=str(output/'11-narrow-navigation.png'),full_page=False);artifacts.append('11-narrow-navigation.png')
            checks.append('All six destinations remain reachable in the sticky narrow navigation')
            # Exercise the new permanent status panel using the REAL job endpoint.
            # The task itself is explicitly synthetic: no game/tools are executed.
            page.set_viewport_size({'width':1440,'height':1120})
            page.locator('nav [data-step="1"]').click()
            def fail_job(log):
                log.phase('tools','TEST: Werkzeugdownload prüfen')
                log.progress(1048576,4194304,'Bytes')
                time.sleep(4)
                raise BuildError('TEST: Verbindung unterbrochen. Originalspiel unverändert.')
            with patch('builtins.print'):
                server.app.start_job(fail_job,action='automation')
                page.wait_for_function("document.querySelector('#jobPhase').textContent.includes('TEST: Werkzeugdownload')",timeout=15000)
                page.wait_for_function("document.querySelector('#jobStatus').textContent.includes('Fehler')",timeout=15000)
            assert page.locator('#jobPanel').is_visible()
            assert 'TEST: Verbindung unterbrochen' in page.locator('#jobError').inner_text()
            page.wait_for_selector('#retryWorkflowBtn:visible',timeout=15000)
            checks.append('Background failure remains visible with phase, history and retry action')
            assert '1 MiB / 4 MiB' in page.locator('#jobCounts').inner_text()
            checks.append('Progress counter displays measured bytes, not invented completion')
            assert page.locator('#pauseJobBtn').is_hidden()
            if page.locator('#toast').is_visible():page.click('#closeToast')
            page.locator('#jobPanel').scroll_into_view_if_needed()
            page.screenshot(path=str(output/'05-diagnostics.png'),full_page=False);artifacts.append('05-diagnostics.png')
            assert wait_download(page,'#diagnosticBtn',bridge)=='TCS-Diagnose-0.4.0.json'
            checks.append('Diagnostic export works from persistent error panel')
            # Retry must actually call /automation/continue, not just dismiss the toast.
            def retry(log):
                log.phase('verify_stage','TEST: geprüften Zwischenschritt wiederverwenden')
                return {'waiting':True,'missing':['TEST: Modarchiv fehlt']}
            page.on('dialog',lambda d:d.accept())
            with patch.object(server.app.workflow,'resume',side_effect=retry) as resume:
                page.click('#retryWorkflowBtn')
                page.wait_for_function("document.querySelector('#jobStatus').textContent.includes('Wartet')",timeout=15000)
                assert resume.call_count==1
            assert page.locator('#jobError').is_hidden()
            checks.append('Retry button reaches backend resume and clears stale error only after success')
            page.click('#pauseJobBtn')
            page.wait_for_function("document.querySelector('#watchStatus').textContent.includes('pausiert')")
            assert not server.app.engine.state['automation']['armed']
            checks.append('Pause button disables automatic imports and write permission')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+2')
            checks.append('Persistent log and error panel also fit a narrow viewport')
            # 0.3.2 regression: actual production preparation with a simulated
            # QuickBMS transport, synthetic DAT contents, no commercial files.
            from test_original_runtime_filter import SimulatedQuickBMS, DATA, PROGRAMS
            from preparation import extract_one, stage_preparation, commit_preparation, restore_preparation
            from engine import digest, Engine
            original = f.root/'original-game-test'; original.mkdir()
            (original/'LEGOStarWarsSaga.exe').write_bytes(b'MZ'+b'\x00'*126)
            (original/'binkw32.dll').write_bytes(b'MZ-keep-this-original-runtime')
            (original/'GAME.DAT').write_text(json.dumps({**PROGRAMS, **DATA}))
            before_dll = digest(original/'binkw32.dll'); before_dat = digest(original/'GAME.DAT')
            page.set_viewport_size({'width':1440,'height':1120})
            page.locator('nav [data-step="1"]').click()
            page.fill('#gamePath', str(original)); page.click('#checkGameBtn')
            page.wait_for_function("document.querySelector('#gameStatus').textContent.includes('automatisch')")
            assert 'BINKW32.DLL' in page.locator('#originalDataPolicy').inner_text()
            checks.append('Original-DAT policy visibly explains the BINKW32.DLL fix without deleting DLLs')
            page.evaluate("document.getElementById('demoLabel').textContent='TESTDATEN · simulierter Archivprozess · kein Windows-/Spieltest'")
            simulation=SimulatedQuickBMS()
            def run_original_preparation(log):
                def extractor(a,o,l):return extract_one(f.root/'simulation.exe',f.root/'simulation.bms',a,o,l)
                manifest=stage_preparation(str(original),server.app.engine.local,log,extractor=extractor)
                return commit_preparation(manifest,server.app.engine.local,log)
            with patch('preparation.run_process',side_effect=simulation), patch.object(Engine,'_running',return_value=False):
                server.app.start_job(run_original_preparation,action='prepare')
                page.wait_for_function("document.querySelector('#originalFilterStatus').textContent.includes('BINKW32.DLL')",timeout=15000)
                page.wait_for_function("document.querySelector('#jobStatus').textContent.includes('abgeschlossen')",timeout=15000)
            assert page.locator('#jobError').is_hidden()
            assert '3 Programmdatei(en)' in page.locator('#originalFilterStatus').inner_text()
            assert (original/'CHARS/BOBA/BOBA.TXT').is_file()
            assert digest(original/'binkw32.dll')==before_dll
            checks.append('Production preparation with synthetic runtime-bearing DAT succeeds and preserves installed DLL')
            assert server.app.diagnostic()['job']['original_filter']['excluded_count']==3
            checks.append('Persistent exclusion count and DLL names included in diagnostic summary')
            page.locator('#jobDetails').evaluate('e=>e.open=true')
            page.locator('#jobPanel').scroll_into_view_if_needed()
            page.screenshot(path=str(output/'06-original-filter.png'),full_page=False);artifacts.append('06-original-filter.png')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+2')
            checks.append('Original-data exclusion panel fits narrow viewport')
            restore_preparation(str(original),lambda _:None)
            assert digest(original/'GAME.DAT')==before_dat and digest(original/'binkw32.dll')==before_dll
            checks.append('Synthetic original-DAT rollback preserves runtime and returns source archive')
            # 0.3.3: real native parser, real binary synthetic PAKs. No
            # external-process simulator is used for this new regression path.
            from test_pak_bounds import make_pak, user_shape, KASHYYYK
            native = f.root/'native-pak-game'; native.mkdir()
            (native/'LEGOStarWarsSaga.exe').write_bytes(b'MZ'+b'\x00'*126)
            (native/'binkw32.dll').write_bytes(b'MZ-preserve-original')
            binary_payload = {'CHARS/BOBA.TXT': b'boba', 'STUFF/ICONS.TXT': b'icons',
                              'LEVELS/TEST.TXT': b'level', KASHYYYK:user_shape()[0],
                              'BINKW32.DLL':b'MZ-do-not-copy'}
            (native/'GAME.DAT').write_bytes(make_pak(binary_payload))
            native_hash=digest(native/'GAME.DAT'); runtime_hash=digest(native/'binkw32.dll')
            page.set_viewport_size({'width':1440,'height':1120})
            page.locator('nav [data-step="1"]').click()
            page.fill('#gamePath',str(native)); page.click('#checkGameBtn')
            page.wait_for_function("document.querySelector('#gameStatus').textContent.includes('automatisch')")
            page.evaluate("document.getElementById('demoLabel').textContent='BINÄRE TEST-PAKs · echter lokaler Parser · kein Originalspiel'")
            def native_preparation(log):
                staged=stage_preparation(str(native),server.app.engine.local,log)
                return commit_preparation(staged,server.app.engine.local,log)
            with patch.object(Engine,'_running',return_value=False), patch('preparation.Tools.quickbms',side_effect=AssertionError('Native fixture must not need external tools')):
                server.app.start_job(native_preparation,action='prepare')
                page.wait_for_function("document.querySelector('#pakCheckStatus').textContent.includes('2 Archive')",timeout=15000)
                page.wait_for_function("document.querySelector('#jobStatus').textContent.includes('abgeschlossen')",timeout=15000)
            assert page.locator('#jobError').is_hidden()
            assert (native/str(Path(KASHYYYK).parent)/'TAIL.TXT').read_bytes()==b'0123456789abc'
            checks.append('Native binary PAK table and 13-byte last entry passed without a QuickBMS process')
            summary=server.app.diagnostic()['job']['pak_checks']
            assert summary['archives_checked']==2 and summary['native_archives']==2 and summary['short_entries']>=1
            checks.append('PAK counts and short-entry handling persist in UI and diagnostic summary')
            page.locator('#jobDetails').evaluate('e=>e.open=true')
            page.locator('#jobPanel').scroll_into_view_if_needed()
            page.click('#checkGameBtn')
            page.wait_for_function("document.querySelector('#gameStatus').textContent.includes('Lose Spieldaten vorhanden')")
            page.locator('#jobPanel').scroll_into_view_if_needed()
            page.screenshot(path=str(output/'07-pak-bounds.png'),full_page=False);artifacts.append('07-pak-bounds.png')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+2')
            checks.append('New PAK summary fits narrow viewport without horizontal overflow')
            restore_preparation(str(native),lambda _:None)
            assert digest(native/'GAME.DAT')==native_hash and digest(native/'binkw32.dll')==runtime_hash
            checks.append('Native nested PAK preparation rollback returns unchanged original container and runtime')
            # 0.4: persistent multi-stage indicators are driven by the actual API.
            from server import JobReporter
            server.app.workflow.message='DEMO: Dateien werden kontrolliert übernommen. Noch nichts im Spiel getestet.'
            server.app.steps.reset()
            server.app.steps.update('prepare','done','Originaldaten und PAKs geprüft; Sicherung vorhanden')
            server.app.steps.update('downloads','running','Refinement Overhaul: Archivinhalt prüfen',{'done':3,'total':4,'unit':'Archive'})
            server.app.steps.update('mapping','waiting','2 von 4 aktivierten Varianten zugeordnet',{'done':2,'total':4,'unit':'Module'})
            page.set_viewport_size({'width':1440,'height':1120})
            page.locator('nav [data-step="1"]').click()
            page.evaluate("loadState(false)")
            page.wait_for_function("document.querySelector('[data-stage=downloads] .stage-value').textContent.includes('75 %')")
            assert page.locator('[data-stage="prepare"] .stage-label').inner_text()=='Fertig'
            assert page.locator('[data-stage="mapping"] .stage-value').inner_text().startswith('50 %')
            assert page.locator('#journeyCount').inner_text()=='1 / 7 Schritte fertig'
            checks.append('Independent 100%, 75% and 50% subtasks displayed without total-progress fiction')
            server.app.steps.update('downloads','running','Dateiliste prüfen: Gesamtmenge noch offen')
            page.evaluate('loadState(false)')
            page.wait_for_function("document.querySelector('[data-stage=downloads] .stage-value').textContent.includes('Gesamtmenge')")
            assert page.locator('[data-stage="downloads"] [role="progressbar"]').get_attribute('aria-valuenow') is None
            assert page.locator('[data-stage="prepare"] .stage-label').inner_text()=='Fertig'
            checks.append('Unknown total is explicit and does not erase completed preparation')
            server.app.steps.update('downloads','running','Archivdateien vergleichen',{'done':30,'total':100,'unit':'Dateien'})
            page.evaluate('loadState(false)')
            page.wait_for_function("document.querySelector('[data-stage=downloads] .stage-value').textContent.includes('30 %')")
            assert page.locator('#progress').is_hidden()
            checks.append('Old oscillating progress overlay remains hidden')
            page.evaluate("document.getElementById('demoLabel').textContent='OBERFLÄCHENTEST · künstliche Daten · kein Spieltest'")
            page.evaluate('refreshAuto()')
            page.evaluate('window.scrollTo(0,0)')
            page.locator('#journeyPanel').scroll_into_view_if_needed()
            page.screenshot(path=str(output/'08-step-progress.png'),full_page=False);artifacts.append('08-step-progress.png')
            page.locator('nav [data-step="2"]').click()
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(output/'09-download-workflow.png'),full_page=False);artifacts.append('09-download-workflow.png')
            assert page.locator('[data-module="infinities-vader-patch"] [data-enabled]').is_checked() is False
            checks.append('Optional Vader patch remains disabled by default')
            page.locator('nav [data-step="5"]').click()
            assert page.locator('#playCheckedBtn').is_disabled()
            assert page.locator('#confirmGameBtn').is_disabled()
            checks.append('Play and game-tested actions unavailable without installed/started build')
            # Read-only final verification through real HTTP endpoint on a synthetic
            # installation generated by the production engine (no Windows launch).
            server.app.engine.state['game']=str(f.game)
            settings=server.app.engine.state.copy();settings['game']=str(f.game)
            settings['options'].update(clean_target_confirmed=True,prepared_confirmed=True,baseline_confirmed=True)
            plan=server.app.engine.make_plan(settings,lambda _:None)
            assert plan['counts']['conflicts']==0
            with patch.object(Engine,'_running',return_value=False):server.app.engine.install(plan,lambda _:None)
            page.evaluate('loadState(false)')
            page.click('#verifyBtn')
            page.wait_for_function("document.querySelector('#readinessStatus').textContent.includes('installierte Dateien geprüft')",timeout=15000)
            assert not page.locator('#playCheckedBtn').is_disabled()
            assert page.locator('#confirmGameBtn').is_disabled()
            checks.append('Real synthetic installation is hash-verified through UI, but does not certify gameplay')
            (f.game/'CHARS/Boba/Body.gsc').write_bytes(b'changed after installation')
            with patch('builtins.print'):
                page.click('#verifyBtn')
                page.wait_for_function("document.querySelector('#jobError').textContent.includes('START_NOT_READY')",timeout=15000)
            assert (f.game/'CHARS/Boba/Body.gsc').read_bytes()==b'changed after installation'
            assert server.app.engine.state.get('readiness') is None
            checks.append('Changed installed file blocks final verification without overwriting it')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+2')
            checks.append('Stage cards and completion controls remain responsive at 390px')
            browser.close()
        if errors:raise AssertionError(errors)
        checks.append('No browser JavaScript exceptions')
        report={'passed':True,'checks':checks,'count':len(checks),'screenshots':artifacts,
                'environment':f'{sys.platform} Chromium via Playwright','transport_adapter_used':bridge,'browser_navigation_session_bootstrap_tested':not bridge,'browser_os_download_tested':not bridge,'test_data':'synthetic only','real_mod_archives_tested':False,'windows_tested':False}
        (output/'BROWSER_TEST_REPORT.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps(report,indent=2,ensure_ascii=False))
    finally:
        print('CLEANUP server',flush=True)
        server.shutdown();server.server_close()
        print('CLEANUP thread',flush=True);thread.join(timeout=5)
        if thread.is_alive():raise RuntimeError('Test HTTP server did not terminate')
        print('CLEANUP fixture',flush=True);f.close()
        print('CLEANUP complete',flush=True)
if __name__=='__main__':main()
