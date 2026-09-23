"""0.4 regressions. Synthetic data; Windows 7-Zip output is simulated explicitly."""
from __future__ import annotations
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from helpers import Fixture, BASE
from safety import BuildError, unpack_external
from matching import roots_for_recipe, assess, identify
from steps import StepTracker
from server import App, JobReporter
from engine import digest, META, Engine, EXE
from readiness import verify_installation
from desktop import window_command, open_window

QUIET=lambda _:None

class ArchiveCompare04Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.archive=self.root/'patch.7z';self.archive.write_bytes(b'synthetic')
        self.work=self.root/'unpacked';self.work.mkdir()
    def tearDown(self):self.temp.cleanup()
    def run_archive(self,listing,files,extra_dir=None):
        def run(args,**kw):
            if args[1]=='l':return subprocess.CompletedProcess(args,0,listing.encode('utf-8'),b'')
            out=Path(next(x[2:] for x in args if x.startswith('-o')))
            for rel,value in files.items():
                p=out/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(value)
            if extra_dir:(out/extra_dir).mkdir(parents=True)
            return subprocess.CompletedProcess(args,0,b'',b'')
        with patch('safety.find_7zip',return_value='7z'),patch('safety.subprocess.run',side_effect=run):
            return unpack_external(self.archive,self.work,QUIET)
    def listing(self,records):
        return '\n\n'.join(f'Path = {p}\nSize = {n}\nAttributes = {a}' for p,n,a in records)+'\n'
    def test_windows_backslash_matches_posix_actual(self):
        listing=self.listing([(r'Common\CHARS\VADER\test.gsc',3,'A'),(r'Classic Icons\STUFF\icon.txt',0,'A')])
        out=self.run_archive(listing,{'Common/CHARS/VADER/test.gsc':b'abc','Classic Icons/STUFF/icon.txt':b''})
        self.assertEqual((out/'Common/CHARS/VADER/test.gsc').read_bytes(),b'abc')
    def test_mixed_case_and_separators(self):
        out=self.run_archive(self.listing([(r'CHARS\A.TXT',3,'A')]),{'chars/a.txt':b'abc'})
        self.assertTrue(out.is_dir())
    def test_directory_rows_not_counted(self):
        out=self.run_archive(self.listing([('Common',0,'D_ drwxr-xr-x'),('Common/CHARS/a.txt',0,'A_ -rw-r--r--')]),{'Common/CHARS/a.txt':b''})
        self.assertTrue(out.is_dir())
    def test_each_size_not_just_total(self):
        with self.assertRaisesRegex(BuildError,'2 falsche Größen'):
            self.run_archive(self.listing([('CHARS/a.txt',1,'A'),('CHARS/b.txt',3,'A')]),{'CHARS/a.txt':b'aa','CHARS/b.txt':b'bb'})
    def test_missing_report(self):
        with self.assertRaisesRegex(BuildError,'1 fehlen'):
            self.run_archive(self.listing([('CHARS/a.txt',1,'A')]),{})
        self.assertEqual(list(self.work.iterdir()),[])
    def test_extra_report(self):
        with self.assertRaisesRegex(BuildError,'1 unerwartet'):
            self.run_archive(self.listing([('CHARS/a.txt',1,'A')]),{'CHARS/a.txt':b'a','CHARS/x.txt':b'x'})
    def test_negative_size_rejected(self):
        with self.assertRaises(BuildError):self.run_archive(self.listing([('CHARS/a.txt',-1,'A')]),{})
    def test_non_numeric_size_rejected(self):
        with self.assertRaises(BuildError):self.run_archive('Path = CHARS/a.txt\nSize = potato\n',{})
    def test_duplicate_different_slashes_rejected(self):
        with self.assertRaises(BuildError):self.run_archive(self.listing([(r'CHARS\a.txt',1,'A'),('CHARS/a.txt',1,'A')]),{})
    def test_escape_still_rejected(self):
        with self.assertRaises(BuildError):self.run_archive(self.listing([(r'..\outside',1,'A')]),{})
    def test_ads_still_rejected(self):
        with self.assertRaises(BuildError):self.run_archive(self.listing([('CHARS/a:stream',1,'A')]),{})
    def test_links_still_rejected(self):
        with self.assertRaises(BuildError):self.run_archive('Path = CHARS/a\nSize = 1\nSymbolic Link = /tmp\n',{})
    def test_zero_size_entry_preserved(self):
        out=self.run_archive(self.listing([('STUFF/empty.txt',0,'A')]),{'STUFF/empty.txt':b''})
        self.assertEqual((out/'STUFF/empty.txt').stat().st_size,0)
    def test_unicode_normalized_only_separators(self):
        out=self.run_archive(self.listing([(r'Gemeinsam\CHARS\Öbi.txt',2,'A')]),{'Gemeinsam/CHARS/Öbi.txt':b'hi'})
        self.assertTrue((out/'Gemeinsam/CHARS/Öbi.txt').is_file())
    def test_old_comparison_reproduces_false_negative(self):
        old_names={r'Common\CHARS\VADER\test.gsc'.casefold()}
        actual={'Common/CHARS/VADER/test.gsc'.casefold()}
        self.assertNotEqual(old_names,actual)

class Mapping04Tests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.modules=self.f.engine.profile['modules']
    def tearDown(self):self.f.close()
    def test_vader_parent_not_rejected(self):
        roots=['Vader Enhancer/Shared','Vader Enhancer/Classic Icons','Vader Enhancer/MO Icons']
        self.assertEqual(roots_for_recipe(roots,'classic'),roots[:2])
    def test_parent_named_icons_does_not_hide_shared(self):
        roots=['Compatibility Icons/Common','Compatibility Icons/Classic','Compatibility Icons/Modern Icons']
        self.assertEqual(roots_for_recipe(roots,'classic'),roots[:2])
    def test_two_classic_children_require_review(self):
        self.assertEqual(roots_for_recipe(['Patch/Common','Patch/Classic 1','Patch/Classic 2'],'classic'),[])
    def test_optional_only_still_rejected(self):
        self.assertEqual(roots_for_recipe(['Optional/Film Accurate'],'main'),[])
    def test_vader_file_identified_separately(self):
        m=identify('Compatibility Patches - Vader Enhancer Addon-133-1-0-1770092331.7z',self.modules)
        self.assertEqual(m['id'],'infinities-vader-patch');self.assertTrue(assess('Compatibility Patches - Vader Enhancer Addon-133-1-0-1770092331.7z',m)['matches'])
    def test_new_version_not_silently_used(self):
        m=next(m for m in self.modules if m['id']=='infinities-al-patch')
        r=assess('Compatibility Patches - Additional Levels-133-9-0-1770092331.7z',m)
        self.assertFalse(r['matches']);self.assertEqual(r['observed_version'],'9.0')
    def test_duplicate_download_suffix(self):
        m=next(m for m in self.modules if m['id']=='infinities-al-patch')
        self.assertTrue(assess('Compatibility Patches - Additional Levels-133-1-1-1770092331 (2).7z',m)['matches'])
    def test_wrong_patch_not_mapped_by_hint(self):
        app=App(self.f.base);app.workflow.configure({'auto_mapping':True})
        p=self.f.root/'Compatibility Patches - Vader Enhancer Addon'
        (p/'Common/CHARS').mkdir(parents=True);(p/'Common/CHARS/a.txt').write_text('a')
        (p/'Classic Icons/STUFF').mkdir(parents=True);(p/'Classic Icons/STUFF/a.txt').write_text('a')
        item=app.workflow.import_data(str(p),log=QUIET,module_id='infinities-al-patch')
        self.assertTrue(app.engine.state['selections']['infinities-vader-patch']['confirmed'])
        self.assertFalse(app.engine.state['selections']['infinities-vader-patch']['enabled'])
        self.assertFalse(app.engine.state['selections']['infinities-al-patch']['source_id'])
    def test_filename_does_not_prove_authenticity(self):
        m=self.modules[0];self.assertFalse(assess(m['watch_names'][0]+'.zip',m)['authenticity_verified'])
    def test_local_mods_plus_downloads(self):
        app=App(self.f.base);d=self.f.root/'Downloads';d.mkdir();app.workflow.configure({'watch_folder':str(d),'watch_local_mods':True})
        self.assertEqual(set(app.workflow.watch_folders()),{str(d),str(self.f.base/'mods')})
    def test_optional_error_does_not_stop_other_imports(self):
        app=App(self.f.base);app.workflow.on_failure('synthetic failure','watch-import')
        self.assertFalse(app.workflow.watch_paused);self.assertFalse(app.engine.state['automation']['armed'])

class Progress04Tests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.app=App(self.f.base);self.log=JobReporter(self.app,self.app.job)
    def tearDown(self):self.f.close()
    def stage(self,key):return next(s for s in self.app.steps.public()['stages'] if s['id']==key)
    def test_suboperation_100_does_not_complete_stage(self):
        self.log.stage('prepare','running','Extract');self.log.progress(10,10,'Dateien')
        self.assertEqual(self.stage('prepare')['status'],'running');self.assertEqual(self.app.steps.public()['completed'],0)
    def test_unknown_total_not_faked(self):
        self.log.stage('prepare','running','QuickBMS');self.assertIsNone(self.stage('prepare')['progress'])
    def test_finished_stage_not_changed_by_next_step(self):
        self.log.stage('prepare','done','Prepared');self.log.phase('unpack_mod','Archive');self.log.progress(2,10,'Dateien')
        self.assertEqual(self.stage('prepare')['status'],'done');self.assertEqual(self.stage('downloads')['progress']['done'],2)
    def test_persisted_completion(self):
        self.log.stage('prepare','done','Prepared');again=StepTracker(self.f.engine.local)
        self.assertEqual(again.public()['completed'],1)
    def test_running_stage_paused_after_restart(self):
        self.log.stage('install','running','Writing');again=StepTracker(self.f.engine.local)
        self.assertEqual(next(s for s in again.public()['stages'] if s['id']=='install')['status'],'paused')
    def test_seven_steps(self):self.assertEqual(self.app.steps.public()['total'],7)
    def test_not_a_time_estimate(self):self.assertFalse(self.app.steps.public()['time_estimate'])
    def test_finished_import_not_finished_install(self):
        self.log.stage('downloads','done','Archive imported');self.assertEqual(self.stage('install')['status'],'pending')

class Readiness04Tests(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();g=self.f.game
        (g/'LEVELS').mkdir(exist_ok=True);(g/'LEVELS/base.txt').write_text('level')
        (g/'STUFF').mkdir(exist_ok=True);(g/'STUFF/base.txt').write_text('stuff')
        (g/'CHARS').mkdir(exist_ok=True);(g/'CHARS/base.txt').write_text('chars')
        self.file=g/'CHARS/mod.txt';self.file.write_text('mod')
        self.journal=g/META/'journal.json';self.journal.parent.mkdir()
        self.data={'schema':1,'status':'INSTALLED','game':str(g),'exe_sha256':digest(g/EXE),
                   'entries':[{'path':'CHARS/mod.txt','after':digest(self.file),'before':None}]}
        self.journal.write_text(json.dumps(self.data))
    def tearDown(self):self.f.close()
    def test_verifies_files_but_not_gameplay(self):
        r=verify_installation(str(self.f.game),{},QUIET)
        self.assertTrue(r['can_launch']);self.assertFalse(r['game_tested']);self.assertEqual(r['checked_files'],1)
    def test_missing_file_blocks_start(self):
        self.file.unlink()
        with self.assertRaisesRegex(BuildError,'START_NOT_READY'):verify_installation(str(self.f.game),{},QUIET)
    def test_changed_file_not_repaired_by_overwrite(self):
        self.file.write_text('my edit')
        with self.assertRaises(BuildError):verify_installation(str(self.f.game),{},QUIET)
        self.assertEqual(self.file.read_text(),'my edit')
    def test_exe_change_blocks_start(self):
        (self.f.game/EXE).write_bytes(b'MZchanged')
        with self.assertRaises(BuildError):verify_installation(str(self.f.game),{},QUIET)
    def test_active_dat_blocks_start(self):
        (self.f.game/'GAME.DAT').write_bytes(b'data')
        with self.assertRaises(BuildError):verify_installation(str(self.f.game),{},QUIET)
    def test_incomplete_journal_blocks_start(self):
        self.data['status']='INSTALLING';self.journal.write_text(json.dumps(self.data))
        with self.assertRaises(BuildError):verify_installation(str(self.f.game),{},QUIET)
    def test_graphics_warning(self):
        self.assertTrue(verify_installation(str(self.f.game),{'options':{'graphics':True}},QUIET)['warnings'])
    def test_foreign_journal_game_path_blocked(self):
        self.data['game']=str(self.f.root/'wrong');self.journal.write_text(json.dumps(self.data))
        with self.assertRaises(BuildError):verify_installation(str(self.f.game),{},QUIET)
    def test_no_journal_blocks_start(self):
        self.journal.unlink()
        with self.assertRaises(BuildError):verify_installation(str(self.f.game),{},QUIET)
    def test_path_escape_rejected(self):
        self.data['entries'][0]['path']='../outside';self.journal.write_text(json.dumps(self.data))
        with self.assertRaises(BuildError):verify_installation(str(self.f.game),{},QUIET)

class Window04Tests(unittest.TestCase):
    def test_command_has_own_window(self):
        args=window_command(Path('browser.exe'),'http://127.0.0.1:1234/#abc',Path('installer'))
        self.assertIn('--app=http://127.0.0.1:1234/#abc',args)
        self.assertFalse(any(x in args for x in ('--no-sandbox','--disable-web-security')))
    def test_external_url_not_allowed_as_app(self):
        with self.assertRaises(ValueError):window_command(Path('browser'),'https://evil.example',Path('installer'))
    def test_browser_fallback(self):
        with patch('desktop.find_browser',return_value=None),patch('desktop.webbrowser.open') as w:
            self.assertEqual(open_window('http://127.0.0.1:1234/#abc',Path('installer')),'browser-fallback');w.assert_called_once()
    def test_spaces_not_shell_interpreted(self):
        args=window_command(Path('C:/path with spaces/chrome.exe'),'http://127.0.0.1:1234/#abc',Path('C:/user & dir'))
        self.assertEqual(Path(args[0]),Path('C:/path with spaces/chrome.exe'));self.assertEqual(len(args),6)



class Integration04Tests(unittest.TestCase):
    def setUp(self):self.f=Fixture()
    def tearDown(self):self.f.close()
    def test_prepared_old_session_migrates_stage(self):
        self.f.engine.state['game']=str(self.f.game);self.f.engine.save()
        app=App(self.f.base)
        self.assertEqual(next(s for s in app.steps.public()['stages'] if s['id']=='prepare')['status'],'done')
    def test_installed_resume_does_not_install_twice(self):
        app=App(self.f.base);app.engine.state['installed_game']=str(self.f.game)
        with patch.object(app.workflow,'verify',return_value={'can_launch':True}) as verify,patch.object(app.workflow,'arm',side_effect=AssertionError('No double install')):
            self.assertTrue(app.workflow.resume(QUIET)['installed']);verify.assert_called_once()
    def test_failed_verify_clears_previous_ready(self):
        app=App(self.f.base);app.engine.state['game']=str(self.f.game);app.engine.state['readiness']={'can_launch':True}
        with self.assertRaises(BuildError):app.workflow.verify(QUIET)
        self.assertNotIn('readiness',app.engine.state)
    def test_conflicting_import_version_requires_review(self):
        app=App(self.f.base);app.workflow.configure({'auto_mapping':True})
        for index in range(2):
            folder=self.f.root/('Lego Star Wars The Complete Saga Modern Overhaul '+str(index));(folder/'Main/CHARS').mkdir(parents=True);(folder/'Main/CHARS/a.txt').write_text(str(index))
            item=app.workflow.import_data(str(folder),log=QUIET)
        choice=app.engine.state['selections']['modern-overhaul']
        self.assertFalse(choice['confirmed']);self.assertIn('Zweite',item['review_reason'])
    def test_dependency_not_enabled_not_ready(self):
        app=App(self.f.base)
        p=self.f.root/'Compatibility Patches - Vader Enhancer Addon';(p/'Common/CHARS').mkdir(parents=True);(p/'Classic Icons/STUFF').mkdir(parents=True)
        (p/'Common/CHARS/a.txt').write_text('a');(p/'Classic Icons/STUFF/a.txt').write_text('b')
        app.workflow.configure({'auto_mapping':True});app.workflow.import_data(str(p),log=QUIET)
        rows=app.workflow.inventory();v=next(r for r in rows if r['id']=='infinities-vader-patch');self.assertFalse(v['ready'])
    def test_archive_recovery_does_not_force_extract(self):
        from diagnostics import recovery_hint
        r=recovery_hint('ARCHIVE_MISMATCH');self.assertFalse(r['automatic']);self.assertEqual(r['code'],'ARCHIVE_LAYOUT_MISMATCH')
    def test_hash_failure_never_waived(self):
        from diagnostics import recovery_hint
        r=recovery_hint('SHA-256 stimmt nicht');self.assertFalse(r['automatic']);self.assertIn('abschalten',r['instruction'])



class WatchEndToEnd04Tests(unittest.TestCase):
    def test_two_folders_import_without_clicking_each_archive(self):
        import zipfile,time
        f=Fixture();app=App(f.base);download=f.root/'downloads';download.mkdir()
        try:
            app.workflow.configure({'watch_enabled':True,'watch_folder':str(download),'auto_mapping':True})
            archives=[(download/'Lego Star Wars The Complete Saga Modern Overhaul-54-2-2-2-1770092331.zip',{'Main/CHARS/a.txt':b'demo'}),
                      (f.base/'mods'/'Compatibility Patches - Vader Enhancer Addon-133-1-0-1770092331.zip',{'Common/CHARS/a.txt':b'patch','Classic Icons/STUFF/icon.txt':b'icon'})]
            for path,files in archives:
                with zipfile.ZipFile(path,'w') as z:
                    for rel,data in files.items():z.writestr(rel,data)
                # Advance only the previously observed stable timestamp. The actual
                # watcher, worker jobs, zip extraction and routing below are real.
                st=path.stat();app.workflow.watch.seen[str(path)]=((st.st_size,st.st_mtime_ns),time.monotonic()-10)
            app.workflow.start()
            limit=time.monotonic()+15
            while time.monotonic()<limit:
                if len(app.engine.state['sources'])==2 and not app.job['running']:break
                time.sleep(.1)
            self.assertEqual(len(app.engine.state['sources']),2)
            self.assertTrue(app.engine.state['selections']['modern-overhaul']['confirmed'])
            self.assertTrue(app.engine.state['selections']['infinities-vader-patch']['confirmed'])
            self.assertFalse(app.engine.state['selections']['infinities-vader-patch']['enabled'])
            self.assertEqual(len(app.workflow.watch.done),2)
            self.assertFalse((f.game/META).exists())
        finally:
            app.workflow.stop_event.set()
            while app.job['running']:time.sleep(.1)
            f.close()

if __name__=='__main__':unittest.main()
