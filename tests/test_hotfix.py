"""0.3.1 regression suite. Synthetic inputs; NOT a Windows/game playtest."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
from helpers import Fixture
from safety import BuildError, safe_rel
from processes import game_running, parse_tasklist
from diagnostics import Cancelled, redact
from engine import Engine, describe_game, digest, jsonwrite
from server import App
from nettools import NetworkError, download, run_process, allowed_url
from nexus import Nexus, DownloadWatch, norm
from preparation import stage_preparation, commit_preparation, restore_preparation
from updater import apply_update, checked_package
from test_downloads import Response

QUIET=lambda _:None
EXE='LEGOStarWarsSaga.exe'

class ProcessRegressionTests(unittest.TestCase):
    def test_v03_exact_none_lower_bug_reproduced(self):
        old_result=subprocess.CompletedProcess([],0,stdout=None)
        with self.assertRaisesRegex(AttributeError,"NoneType.*lower"):
            EXE.lower() in old_result.stdout.lower()
    def test_german_oem_output_does_not_need_text_decode(self):
        message='INFO: Es werden keine Aufgaben mit den angegebenen Kriterien ausgeführt.'.encode('cp850')
        with self.assertRaises(UnicodeDecodeError):message.decode('cp1252')
        self.assertFalse(parse_tasklist(message,0,EXE))
    def test_running_exe_csv_detected(self):
        self.assertTrue(parse_tasklist(b'"LEGOSTARWARSSAGA.EXE","4534","Console","1","42 K"\r\n',0,EXE))
    def test_matching_only_first_csv_field(self):
        self.assertFalse(parse_tasklist(b'"other.exe","1","LEGOStarWarsSaga.exe"',0,EXE))
    def test_none_output_fails_closed(self):
        with self.assertRaisesRegex(BuildError,'keine Prozessliste'):parse_tasklist(None,0,EXE)
    def test_empty_output_fails_closed(self):
        with self.assertRaises(BuildError):parse_tasklist(b'',0,EXE)
    def test_exit_error_fails_closed(self):
        with self.assertRaises(BuildError):parse_tasklist(b'error',1,EXE)
    def test_unicode_adapter_supported(self):
        self.assertTrue(parse_tasklist('"LEGOStarWarsSaga.exe","2"',0,EXE))
    def test_windows_subprocess_never_uses_text_mode(self):
        with patch('processes.os.name','nt'),patch('processes.subprocess.run',return_value=subprocess.CompletedProcess([],0,b'INFO: no tasks',b'')) as run:
            self.assertFalse(game_running())
        kw=run.call_args.kwargs
        self.assertNotIn('text',kw);self.assertNotIn('encoding',kw)
        self.assertFalse(kw['shell']);self.assertEqual(kw['stdin'],subprocess.DEVNULL)
    def test_timeout_is_actionable(self):
        with patch('processes.os.name','nt'),patch('processes.subprocess.run',side_effect=subprocess.TimeoutExpired('tasklist',20)):
            with self.assertRaisesRegex(BuildError,'lange'):game_running()
    def test_process_start_failure_is_actionable(self):
        with patch('processes.os.name','nt'),patch('processes.subprocess.run',side_effect=OSError('blocked')):
            with self.assertRaises(BuildError):game_running()
    @unittest.skipUnless(os.name=='nt','Requires actual Windows; not replaced by synthetic proof')
    def test_real_windows_tasklist_output_is_readable(self):
        self.assertIsInstance(game_running(),bool)

class NullAndNetworkRegressionTests(unittest.TestCase):
    def test_empty_paths_rejected(self):
        for value in (None,{},'',False):
            with self.subTest(value=value):
                with self.assertRaises(BuildError):describe_game(value)
    def test_null_relative_path_rejected(self):
        with self.assertRaises(BuildError):safe_rel(None)
    def test_null_url_rejected(self):
        with self.assertRaises(BuildError):allowed_url(None,'tool')
    def test_null_nexus_name_is_empty_not_exception(self):
        for value in (None,1,{},[]):self.assertEqual(norm(value),'')
    def test_transient_download_retries_then_succeeds(self):
        with tempfile.TemporaryDirectory() as d,patch('nettools.open_url',side_effect=[NetworkError('timeout'),Response(b'good')]) as req,patch('nettools.time.sleep'):
            p=Path(d)/'a.zip';download('https://github.com/a',p)
            self.assertEqual(p.read_bytes(),b'good');self.assertEqual(req.call_count,2)
    def test_transient_download_attempt_limit(self):
        with tempfile.TemporaryDirectory() as d,patch('nettools.open_url',side_effect=NetworkError('timeout')) as req,patch('nettools.time.sleep'):
            with self.assertRaises(NetworkError):download('https://github.com/a',Path(d)/'a.zip')
            self.assertEqual(req.call_count,3)
    def test_bad_hash_never_retried(self):
        with tempfile.TemporaryDirectory() as d,patch('nettools.open_url',return_value=Response(b'wrong')) as req:
            with self.assertRaises(BuildError):download('https://github.com/a',Path(d)/'a.zip',expected_sha256='0'*64)
            self.assertEqual(req.call_count,1);self.assertEqual(list(Path(d).iterdir()),[])
    def test_cancellation_before_network(self):
        log=Mock();log.check_cancelled.side_effect=Cancelled('pause')
        with tempfile.TemporaryDirectory() as d,patch('nettools.open_url') as req:
            with self.assertRaises(Cancelled):download('https://github.com/a',Path(d)/'a.zip',log=log)
            req.assert_not_called()
    def test_process_returns_bytes(self):
        self.assertEqual(run_process([sys.executable,'-c','import sys;sys.stdout.buffer.write(bytes([129,130]))']),b'\x81\x82')
    def test_process_failure_logs_tail(self):
        messages=[]
        with self.assertRaisesRegex(BuildError,'Fehlercode 4'):
            run_process([sys.executable,'-c','print("synthetic extraction issue");raise SystemExit(4)'],log=messages.append)
        self.assertIn('synthetic extraction issue','\n'.join(messages))
    def test_process_timeout(self):
        with self.assertRaisesRegex(BuildError,'Zeitlimit'):
            run_process([sys.executable,'-c','import time;time.sleep(4)'],timeout=.02)
    def test_nexus_null_catalog_entries_are_ignored(self):
        f=Fixture()
        try:
            n=Nexus(f.engine.profile,f.engine.local)
            entries=[None,{}, {'file_id':583,'category_id':1,'version':'2.2.2','name':None,'file_name':None}]
            with patch.object(n,'api',return_value={'files':entries}):
                self.assertEqual(n.resolve(QUIET)['files'],[])
        finally:f.close()
    def test_nexus_null_download_uri_fails_controlled(self):
        f=Fixture()
        try:
            n=Nexus(f.engine.profile,f.engine.local);n._key='test';n._user={'is_premium':True}
            n.catalog={'m':{'mod_id':54,'file_id':583,'file_name':'mod.zip','name':'demo'}}
            with patch.object(n,'api',return_value=[None,{'URI':None}]):
                with self.assertRaisesRegex(BuildError,'Downloadadresse'):n.fetch('m',QUIET)
        finally:f.close()

class Progress:
    def __init__(self):self.lines=[];self.phases=[];self.counters=[]
    def __call__(self,s):self.lines.append(s)
    def phase(self,key,label):self.phases.append(key)
    def progress(self,done,total,unit='Dateien'):self.counters.append((done,total,unit))
    def check_cancelled(self):pass

class ResumeRegressionTests(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();self.game=self.f.game;self.local=self.f.engine.local;self.calls=[]
        for name in ('CHARS','STUFF','LEVELS'):shutil.rmtree(self.game/name)
        self.payload={'CHARS/a.txt':'a','STUFF/b.txt':'b','LEVELS/c.txt':'c'}
        (self.game/'GAME.DAT').write_text(json.dumps(self.payload))
    def tearDown(self):self.f.close()
    def extract(self,archive,folder,log):
        self.calls.append(archive.name);folder.mkdir();records={}
        for name,text in json.loads(archive.read_text()).items():
            p=folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            records[name.casefold()]={'path':name,'source':str(p),'bytes':p.stat().st_size,'sha256':digest(p)}
        return records
    def stage(self,log=QUIET,extractor=None):
        return stage_preparation(str(self.game),self.local,log,extractor=extractor or self.extract)
    def test_complete_stage_reused_without_extractor(self):
        first=self.stage();second=self.stage(extractor=Mock(side_effect=AssertionError('must reuse')))
        self.assertEqual(first,second);self.assertEqual(self.calls,['GAME.DAT'])
    def test_changed_cached_stage_blocks_instead_of_installing(self):
        m=self.stage();data=json.loads(m.read_text());Path(data['files'][0]['source']).write_text('tampered')
        with self.assertRaises(BuildError):self.stage()
        self.assertTrue((self.game/'GAME.DAT').exists());self.assertFalse((self.game/'CHARS').exists())
    def test_interrupted_second_archive_reuses_first(self):
        (self.game/'GAME1.DAT').write_text(json.dumps({'LEVELS/d.txt':'d'}))
        failed=[False]
        def interrupted(a,o,l):
            if a.name=='GAME1.DAT' and not failed[0]:failed[0]=True;raise BuildError('synthetic interruption')
            return self.extract(a,o,l)
        with self.assertRaises(BuildError):self.stage(extractor=interrupted)
        m=self.stage();self.assertTrue(m.is_file())
        self.assertEqual(self.calls.count('GAME.DAT'),1);self.assertEqual(self.calls.count('GAME1.DAT'),1)
    def test_incomplete_extraction_dir_rebuilt(self):
        def partial(a,o,l):o.mkdir();(o/'partial.txt').write_text('partial');raise BuildError('interruption')
        with self.assertRaises(BuildError):self.stage(extractor=partial)
        m=self.stage();self.assertTrue(m.is_file());self.assertFalse(list(m.parent.rglob('partial.txt')))
    def test_changed_original_uses_different_cache(self):
        a=self.stage();(self.game/'GAME.DAT').write_text(json.dumps({**self.payload,'CHARS/extra.txt':'extra'}));b=self.stage()
        self.assertNotEqual(a,b);self.assertEqual(len(self.calls),2)
    def test_hash_progress_reports_real_bytes(self):
        log=Progress();self.stage(log)
        self.assertIn('hash_originals',log.phases)
        size=(self.game/'GAME.DAT').stat().st_size
        self.assertIn((size,size,'Bytes'),log.counters)
    def test_full_synthetic_automatic_prepare_install_restore(self):
        app=App(self.f.base);w=app.workflow;e=app.engine
        e.state['game']=str(self.game);e.state['options']['clean_target_confirmed']=True
        w.configure({'allow_tools':True,'auto_mapping':True,'desktop_shortcut':False,'auto_watch':False})
        names=['modern-overhaul','additional-levels-mo','infinities','infinities-al-patch']
        for mid in names:
            p=self.f.root/(mid+'.zip')
            with zipfile.ZipFile(p,'w') as z:
                if mid.startswith('infinities'):
                    z.writestr('Common/CHARS/'+mid+'.txt','new');z.writestr('Classic Icons/STUFF/'+mid+'.txt','classic')
                else:z.writestr('Main/LEVELS/'+mid+'.txt','synthetic')
            w.import_data(str(p),p.name,QUIET,mid,{'module':mid,'mod_id':next(m['nexus']['mod_id'] for m in e.profile['modules'] if m['id']==mid)})
        self.assertEqual(w.missing(),[])
        original=digest(self.game/'GAME.DAT');exe_hash=digest(self.game/EXE)
        def synthetic_stage(g,l,log,tools=None):return stage_preparation(g,l,log,extractor=self.extract)
        with patch('workflow.require_windows'),patch('workflow.stage_preparation',side_effect=synthetic_stage),patch.object(Engine,'_running',return_value=False):
            result=w.arm('PREPARE_AND_INSTALL',QUIET)
            self.assertTrue(result['status'].startswith('INSTALLED'))
            self.assertTrue((self.game/'LEVELS/modern-overhaul.txt').is_file())
            self.assertFalse(e.state['automation']['armed'])
            w.restore(str(self.game),False,QUIET);w.restore(str(self.game),True,QUIET)
        self.assertEqual(digest(self.game/'GAME.DAT'),original);self.assertEqual(digest(self.game/EXE),exe_hash)
        self.assertFalse((self.game/'CHARS').exists())

class AutomationRegressionTests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.app=App(self.f.base);self.w=self.app.workflow
    def tearDown(self):self.f.close()
    def test_resume_reenters_preparation_not_just_install(self):
        with patch.object(self.w,'arm',return_value={'waiting':True}) as arm:
            self.assertTrue(self.w.resume(QUIET)['waiting'])
            arm.assert_called_once_with('PREPARE_AND_INSTALL',QUIET)
    def test_prepared_flag_not_left_true_after_failure(self):
        (self.f.game/'GAME.DAT').write_bytes(b'dat');e=self.app.engine
        e.state['options'].update(prepared_confirmed=True,clean_target_confirmed=True);self.w.configure({'allow_tools':True})
        with patch('workflow.require_windows'),patch('workflow.stage_preparation',side_effect=BuildError('blocked')):
            with self.assertRaises(BuildError):self.w.prepare(str(self.f.game),QUIET)
        self.assertFalse(e.state['options']['prepared_confirmed'])
    def test_null_session_settings_repaired(self):
        jsonwrite(self.f.engine.local/'session.json',{'game':None,'options':None,'automation':None,'selections':None,'decisions':None,'sources':None})
        e=Engine(self.f.base);self.assertIsInstance(e.state['options'],dict)
    def test_watch_failure_requires_explicit_retry(self):
        folder=self.f.root/'downloads';folder.mkdir();(folder/'Refinement Overhaul.zip').write_bytes(b'a')
        watch=self.w.watch;watch.candidates(str(folder),now=0);item=watch.candidates(str(folder),now=9)[0];watch.mark_failed(item)
        self.assertEqual(watch.candidates(str(folder),now=19),[])
        watch.retry_failed();self.assertEqual(len(watch.candidates(str(folder),now=20)),1)
    def test_partial_sibling_blocks_import(self):
        folder=self.f.root/'downloads';folder.mkdir();(folder/'Refinement Overhaul.zip').write_bytes(b'a');(folder/'Refinement Overhaul.zip.part').write_bytes(b'b')
        self.w.watch.candidates(str(folder),now=0);self.assertEqual(self.w.watch.candidates(str(folder),now=15),[])
    def test_confirmed_archive_mapping_preserved_on_repeat(self):
        p=self.f.root/'Refinement Overhaul.zip'
        with zipfile.ZipFile(p,'w') as z:z.writestr('Common/CHARS/a.txt','a');z.writestr('Classic Icons/STUFF/a.txt','b')
        self.w.configure({'auto_mapping':True})
        one=self.w.import_data(str(p),log=QUIET);two=self.w.import_data(str(p),log=QUIET)
        self.assertEqual(one['id'],two['id']);self.assertTrue(self.app.engine.state['selections']['infinities']['confirmed'])
    def test_missing_mods_wait_without_any_install(self):
        self.app.engine.state['automation']['armed']=True
        with patch.object(self.w,'install') as install:
            result=self.w.maybe_install(QUIET);self.assertEqual(len(result['missing']),4);install.assert_not_called()
    def test_failed_job_disarms_and_pauses_watcher(self):
        self.app.engine.state['automation']['armed']=True;self.w.on_failure('controlled failure')
        self.assertFalse(self.app.engine.state['automation']['armed']);self.assertTrue(self.w.watch_paused)

class DiagnosticsRegressionTests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.app=App(self.f.base)
    def tearDown(self):
        if self.app.job_thread is not None:
            self.app.job_thread.join(timeout=5)
            self.assertFalse(self.app.job_thread.is_alive())
        self.f.close()
    def wait(self):
        until=time.monotonic()+5
        while self.app.job['running'] and time.monotonic()<until:time.sleep(.01)
        self.assertFalse(self.app.job['running'])
        self.app.job_thread.join(timeout=5)
        self.assertFalse(self.app.job_thread.is_alive())
    def test_error_persists_with_phase_and_no_secret(self):
        self.app.workflow.nexus._key='MY-PRIVATE-API-KEY';self.app.engine.state['game']=str(self.f.game)
        def fail(log):
            log.phase('tools','Werkzeuge prüfen');log('https://example.org/?key=TOPSECRET '+str(self.f.game))
            raise AttributeError("'NoneType' object has no attribute 'lower' MY-PRIVATE-API-KEY")
        with patch('builtins.print'):self.app.start_job(fail,action='prepare');self.wait()
        report=json.dumps(self.app.diagnostic())
        self.assertNotIn('TOPSECRET',report);self.assertNotIn('MY-PRIVATE-API-KEY',report);self.assertNotIn(str(self.f.game),report)
        self.assertIn('AttributeError',report);self.assertEqual(self.app.job['phase'],'tools')
        again=App(self.f.base);self.assertEqual(again.last_error['type'],'AttributeError');self.assertEqual(again.job['status'],'error')
    def test_cancel_keeps_job_report(self):
        entered=threading.Event()
        def work(log):
            entered.set()
            while True:log.check_cancelled();time.sleep(.01)
        with patch('builtins.print'):
            self.app.start_job(work,action='prepare');self.assertTrue(entered.wait(2));self.app.request_stop();self.wait()
        self.assertEqual(self.app.job['status'],'cancelled');self.assertTrue(self.app.workflow.watch_paused)
    def test_successful_retry_resolves_prior_error(self):
        with patch('builtins.print'):
            self.app.start_job(lambda log:(_ for _ in ()).throw(BuildError('transient')),action='prepare');self.wait()
        self.app.start_job(lambda log:{'prepared':True},action='prepare');self.wait()
        self.assertTrue(self.app.last_error['resolved']);self.assertEqual(self.app.job['status'],'success')
    def test_restart_does_not_claim_previous_running_job_continues(self):
        jsonwrite(self.app.logs/'last-job.json',{'id':'interrupted','running':True,'status':'running'})
        again=App(self.f.base);self.assertFalse(again.job['running']);self.assertEqual(again.job['status'],'interrupted')
    def test_redaction_removes_usernames_and_urls(self):
        text=redact('C:\\Users\\Jerome\\Documents nxm://legostarwarsthecompletesaga/mods/54/files/1?key=SECRET')
        self.assertNotIn('Jerome',text);self.assertNotIn('SECRET',text)

class UpdaterRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.new=self.root/'new';self.old=self.root/'old'
        self.new.mkdir();self.old.mkdir()
        for root in (self.new,self.old):
            (root/'app').mkdir();(root/'app/server.py').write_text('old-server' if root==self.old else 'new-server')
            (root/'profile.json').write_text(json.dumps({'name':'TCS Remaster · Classic Plus','version':'0.3.1' if root==self.new else '0.3.0'}))
        (self.new/'app/new.py').write_text('new file')
        (self.old/'.local').mkdir();(self.old/'.local/private.zip').write_bytes(b'local-downloaded-data')
        (self.old/'.runtime').mkdir();(self.old/'.runtime/python.exe').write_bytes(b'private-runtime')
        self.names=['app/server.py','app/new.py','profile.json','publish-allowlist.json','SHA256SUMS.txt']
        (self.new/'publish-allowlist.json').write_text(json.dumps({'files':self.names}));self.hashes()
    def hashes(self):
        (self.new/'SHA256SUMS.txt').write_text(''.join(digest(self.new/n)+'  '+n+'\n' for n in self.names if n!='SHA256SUMS.txt'))
    def tearDown(self):self.tmp.cleanup()
    def test_package_checksums_verified(self):self.assertEqual(checked_package(self.new),self.names)
    def test_corrupted_update_rejected_before_write(self):
        (self.new/'app/new.py').write_text('tamper')
        with self.assertRaises(BuildError):apply_update(self.new,self.old,QUIET)
        self.assertEqual((self.old/'app/server.py').read_text(),'old-server')
    def test_preserves_local_downloads_runtime_and_backup(self):
        result=apply_update(self.new,self.old,QUIET)
        self.assertEqual((self.old/'app/server.py').read_text(),'new-server')
        self.assertEqual((self.old/'.local/private.zip').read_bytes(),b'local-downloaded-data')
        self.assertEqual((self.old/'.runtime/python.exe').read_bytes(),b'private-runtime')
        self.assertEqual((Path(result['backup'])/'files/app/server.py').read_text(),'old-server')
    def test_game_folder_never_updated(self):
        (self.old/EXE).write_bytes(b'MZ')
        with self.assertRaisesRegex(BuildError,'Spielordner'):apply_update(self.new,self.old,QUIET)
    def test_running_installer_blocks_update(self):
        with patch('updater.workspace_running',return_value=True):
            with self.assertRaisesRegex(BuildError,'läuft noch'):apply_update(self.new,self.old,QUIET)
    def test_partial_update_rolls_back_code(self):
        with self.assertRaises(BuildError):apply_update(self.new,self.old,QUIET,fail_after=2)
        self.assertEqual((self.old/'app/server.py').read_text(),'old-server');self.assertFalse((self.old/'app/new.py').exists())
        self.assertEqual((self.old/'.local/private.zip').read_bytes(),b'local-downloaded-data')
    def test_private_file_cannot_be_in_update_manifest(self):
        self.names.append('.local/secret.json');(self.new/'.local').mkdir();(self.new/'.local/secret.json').write_text('bad')
        (self.new/'publish-allowlist.json').write_text(json.dumps({'files':self.names}));self.hashes()
        with self.assertRaises(BuildError):apply_update(self.new,self.old,QUIET)
    def test_same_folder_rejected(self):
        with self.assertRaises(BuildError):apply_update(self.new,self.new,QUIET)
