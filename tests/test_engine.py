import json, unittest, zipfile
from pathlib import Path
from helpers import Fixture
from engine import BuildError, META, describe_game, guess_module, suggest_roots

class EngineTests(unittest.TestCase):
    def setUp(self):self.f=Fixture()
    def tearDown(self):self.f.close()
    def p(self,**opts):return self.f.plan(**opts)
    def test_game_detect(self):self.assertTrue(describe_game(str(self.f.game))['prepared_structure'])
    def test_wrong_game_rejected(self):
        (self.f.game/'LEGOStarWarsSaga.exe').unlink()
        with self.assertRaises(BuildError):describe_game(str(self.f.game))
    def test_fake_nonexe_rejected(self):
        (self.f.game/'LEGOStarWarsSaga.exe').write_text('not executable')
        with self.assertRaises(BuildError):describe_game(str(self.f.game))
    def test_no_modules_rejected(self):
        with self.assertRaises(BuildError):self.p()
    def test_dependency(self):
        self.f.add('additional-levels-mo',{'CHARS/a.txt':'x'})
        with self.assertRaises(BuildError):self.p()
    def test_missing_patch(self):
        for m in ('modern-overhaul','additional-levels-mo','infinities'):self.f.add(m,{'CHARS/'+m+'.txt':m})
        with self.assertRaises(BuildError):self.p()
    def test_unconfirmed_source(self):
        self.f.add('modern-overhaul',{'CHARS/a.txt':'x'});self.f.selections['modern-overhaul']['confirmed']=False
        with self.assertRaises(BuildError):self.p()
    def test_main_file_staged(self):
        self.f.add('modern-overhaul',{'CHARS/a.txt':'x'});p=self.p();self.assertEqual(p['counts']['files'],1);self.assertEqual(p['counts']['conflicts'],0)
    def test_identical_dedup(self):
        for m in ('modern-overhaul','additional-levels-mo'):self.f.add(m,{'CHARS/a.txt':'same'})
        p=self.p();self.assertEqual(p['records'][0]['strategy'],'identical-deduplicated');self.assertEqual(p['counts']['conflicts'],0)
    def test_binary_unknown_block(self):
        for m,val in [('modern-overhaul',b'\x00a'),('additional-levels-mo',b'\x00b')]:self.f.add(m,{'STUFF/THINGS_PC.GSC':val})
        p=self.p();self.assertEqual(p['counts']['conflicts'],1)
        with self.assertRaises(BuildError):self.f.engine.make_build(p)
    def test_threeway_nonoverlapping_merges_automatically_with_baseline(self):
        (self.f.game/'CHARS'/'chars.txt').write_bytes(b'a\nb\nc\n')
        self.f.add('modern-overhaul',{'CHARS/chars.txt':'A\nb\nc\n'});self.f.add('additional-levels-mo',{'CHARS/chars.txt':'a\nb\nC\n'})
        self.assertEqual(self.p()['counts']['conflicts'],1)
        p=self.p(baseline_confirmed=True);self.assertEqual(p['counts']['text_merges'],1);self.assertEqual(p['counts']['conflicts'],0)
        self.assertEqual(p['records'][0]['strategy'],'automatic-three-way-text')
        self.assertEqual(self.f.engine.blob(p['records'][0]['result']['sha256']).read_bytes(),b'A\nb\nC\n')
    def test_overlapping_text_block(self):
        (self.f.game/'CHARS'/'chars.txt').write_text('a\nb\n')
        self.f.add('modern-overhaul',{'CHARS/chars.txt':'a\nB\n'});self.f.add('additional-levels-mo',{'CHARS/chars.txt':'a\nC\n'})
        p=self.p(baseline_confirmed=True);self.assertEqual(p['counts']['conflicts'],1)
    def test_known_author_overlay_is_automatic(self):
        self.f.add('modern-overhaul',{'CHARS/Boba/Body.gsc':b'\x00a'});self.f.add('infinities',{'CHARS/Boba/Body.gsc':b'\x00b'})
        p=self.p();self.assertEqual(p['counts']['conflicts'],0);self.assertEqual(p['counts']['recipe_overlays'],1)
        self.assertEqual(p['records'][0]['strategy'],'recipe-overlay');self.assertEqual(p['records'][0]['result']['module'],'infinities')
    def test_recipe_scope_not_arbitrary_text(self):
        self.f.add('modern-overhaul',{'CHARS/a.txt':'a'});self.f.add('infinities',{'CHARS/a.txt':'b'})
        self.assertEqual(self.p()['counts']['conflicts'],1)
    def test_explicit_provider(self):
        self.f.add('modern-overhaul',{'STUFF/A.gsc':'a'});self.f.add('additional-levels-mo',{'STUFF/A.gsc':'b'})
        settings=self.f.settings();settings['decisions']={'stuff/a.gsc':{'type':'provider','module':'modern-overhaul'}}
        p=self.f.engine.make_plan(settings,log=lambda x:None);self.assertEqual(p['counts']['conflicts'],0);self.assertEqual(p['records'][0]['result']['module'],'modern-overhaul')
    def test_explicit_patch(self):
        self.f.add('modern-overhaul',{'STUFF/A.gsc':'a'});self.f.add('additional-levels-mo',{'STUFF/A.gsc':'b'})
        patch=self.f.root/'merged.gsc';patch.write_bytes(b'merged by test')
        s=self.f.settings();s['decisions']={'stuff/a.gsc':{'type':'patch','path':str(patch)}}
        p=self.f.engine.make_plan(s,log=lambda x:None);self.assertEqual(p['records'][0]['strategy'],'explicit-patch-file')
    def test_install_restore(self):
        self.f.add('modern-overhaul',{'CHARS/vanilla.txt':'modded','STUFF/New/sub.txt':'new'})
        p=self.p();r=self.f.engine.install(p,log=lambda x:None);self.assertEqual(r['status'],'INSTALLED_NOT_GAME_TESTED')
        self.assertEqual((self.f.game/'CHARS'/'vanilla.txt').read_text(),'modded')
        self.f.engine.restore(str(self.f.game),log=lambda x:None)
        self.assertEqual((self.f.game/'CHARS'/'vanilla.txt').read_text(),'vanilla\n');self.assertFalse((self.f.game/'STUFF'/'New').exists());self.assertFalse((self.f.game/META).exists())
    def test_install_failure_rolls_back(self):
        self.f.add('modern-overhaul',{'CHARS/vanilla.txt':'changed','STUFF/a.txt':'new'})
        with self.assertRaises(OSError):self.f.engine.install(self.p(),log=lambda x:None,fail_after=0)
        self.assertEqual((self.f.game/'CHARS'/'vanilla.txt').read_text(),'vanilla\n');self.assertFalse((self.f.game/'STUFF'/'a.txt').exists());self.assertFalse((self.f.game/META).exists())
    def test_before_snapshot_changed(self):
        self.f.add('modern-overhaul',{'CHARS/vanilla.txt':'changed'});p=self.p();(self.f.game/'CHARS'/'vanilla.txt').write_text('external')
        with self.assertRaises(BuildError):self.f.engine.install(p,log=lambda x:None)
        self.assertEqual((self.f.game/'CHARS'/'vanilla.txt').read_text(),'external');self.assertFalse((self.f.game/META).exists())
    def test_restore_refuses_later_change(self):
        self.f.add('modern-overhaul',{'CHARS/vanilla.txt':'changed'});self.f.engine.install(self.p(),log=lambda x:None)
        (self.f.game/'CHARS'/'vanilla.txt').write_text('user edit')
        with self.assertRaises(BuildError):self.f.engine.restore(str(self.f.game),log=lambda x:None)
        self.assertTrue((self.f.game/META/'backup'/'CHARS'/'vanilla.txt').exists());self.assertEqual((self.f.game/'CHARS'/'vanilla.txt').read_text(),'user edit')
    def test_restore_missing_backup_refused(self):
        self.f.add('modern-overhaul',{'CHARS/vanilla.txt':'changed'});self.f.engine.install(self.p(),log=lambda x:None)
        (self.f.game/META/'backup'/'CHARS'/'vanilla.txt').unlink()
        with self.assertRaises(BuildError):self.f.engine.restore(str(self.f.game),log=lambda x:None)
    def test_second_install_refused(self):
        self.f.add('modern-overhaul',{'CHARS/vanilla.txt':'changed'});p=self.p();self.f.engine.install(p,log=lambda x:None)
        with self.assertRaises(BuildError):self.f.engine.install(p,log=lambda x:None)
    def test_unprepared_install_refused(self):
        self.f.add('modern-overhaul',{'CHARS/vanilla.txt':'changed'});p=self.p();__import__('shutil').rmtree(self.f.game/'LEVELS')
        with self.assertRaises(BuildError):self.f.engine.install(p,log=lambda x:None)
    def test_unconfirmed_target_refused(self):
        self.f.add('modern-overhaul',{'CHARS/vanilla.txt':'changed'});p=self.p(clean_target_confirmed=False)
        with self.assertRaises(BuildError):self.f.engine.install(p,log=lambda x:None)
    def test_build_zip_layout(self):
        self.f.add('modern-overhaul',{'CHARS/a.txt':'changed'});r=self.f.engine.make_build(self.p(),log=lambda x:None)
        with zipfile.ZipFile(r['archive']) as z:self.assertIn('Redirector/CHARS/a.txt',z.namelist());self.assertIn('ModConfig.json',z.namelist())
    def test_graphics_export_separated(self):
        self.f.add('modern-overhaul',{'CHARS/a.txt':'changed'});r=self.f.engine.make_build(self.p(graphics=True),log=lambda x:None)
        self.assertTrue((Path(r['folder'])/'graphics-for-game-folder'/'TCS_ClassicPlus.ini').is_file())
        with zipfile.ZipFile(r['archive']) as z:self.assertNotIn('Redirector/TCS_ClassicPlus.ini',z.namelist())
    def test_corrupt_object_refused(self):
        self.f.add('modern-overhaul',{'CHARS/a.txt':'changed'});p=self.p();self.f.engine.blob(p['records'][0]['result']['sha256']).write_text('tampered')
        with self.assertRaises(BuildError):self.f.engine.make_build(p,log=lambda x:None)
    def test_publish_excludes_local(self):
        (self.f.engine.local/'private.txt').write_text('secret')
        p=self.f.engine.export_installer()
        with zipfile.ZipFile(p) as z:self.assertFalse(any('.local' in n or 'private' in n for n in z.namelist()));self.assertEqual(len(z.namelist()),2)
    def test_publish_blocks_wrong_allowlist(self):
        (self.f.base/'publish-allowlist.json').write_text(json.dumps({'files':['.local/private.txt']}))
        with self.assertRaises(BuildError):self.f.engine.export_installer()
    def test_publish_blocks_binary(self):
        (self.f.base/'publish-allowlist.json').write_text(json.dumps({'files':['CHARS/a.gsc']}))
        with self.assertRaises(BuildError):self.f.engine.export_installer()
    def test_guess_module(self):
        self.assertEqual(guess_module('Compatibility Patches - Additional Levels-133.zip',[]),'infinities-al-patch');self.assertEqual(guess_module('Refinement Overhaul.zip',[]),'infinities');self.assertIsNone(guess_module('mystery.zip',[]))
    def test_suggest_classic(self):self.assertEqual(suggest_roots(['Common','Classic Icons','MO Icons'],'classic'),['Common','Classic Icons'])
    def test_import_fills_ui_placeholder_selection(self):
        self.f.engine.state['selections']['infinities']={'source_id':'','enabled':True,'roots':[],'confirmed':False}
        source=self.f.add('infinities',{'Common/CHARS/Boba.gsc':b'\x00a','Classic Icons/STUFF/icons.gsc':b'\x00b','MO Icons/STUFF/icons.gsc':b'\x00c'})
        selected=self.f.engine.state['selections']['infinities']
        self.assertEqual(selected['source_id'],source['id']);self.assertEqual(set(selected['roots']),{'Common','Classic Icons'});self.assertFalse(selected['confirmed'])
    def test_import_keeps_existing_assignment(self):
        a=self.f.add('infinities',{'CHARS/a.txt':'first'})
        b=self.f.add('infinities',{'CHARS/b.txt':'second'})
        self.assertNotEqual(a['id'],b['id']);self.assertEqual(self.f.engine.state['selections']['infinities']['source_id'],a['id'])
    def test_executable_changed_after_plan_refused(self):
        self.f.add('modern-overhaul',{'CHARS/a.txt':'mod'})
        plan=self.p();(self.f.game/'LEGOStarWarsSaga.exe').write_bytes(b'MZdifferent')
        with self.assertRaises(BuildError):self.f.engine.install(plan,log=lambda x:None)
        self.assertFalse((self.f.game/META).exists())
    def test_archive_mutation_after_import_refused(self):
        path=self.f.root/'Modern Overhaul.zip'
        with zipfile.ZipFile(path,'w') as z:z.writestr('CHARS/a.txt','before')
        source=self.f.engine.import_source(str(path),log=lambda x:None)
        self.f.selections['modern-overhaul']={'source_id':source['id'],'enabled':True,'confirmed':True,'roots':['']}
        with zipfile.ZipFile(path,'w') as z:z.writestr('CHARS/a.txt','after')
        with self.assertRaises(BuildError):self.p()
    def test_file_blocking_destination_directory_refused(self):
        (self.f.game/'CHARS'/'notadir').write_text('preserve')
        self.f.add('modern-overhaul',{'CHARS/notadir/file.txt':'mod'})
        with self.assertRaises(BuildError):self.p()
        self.assertEqual((self.f.game/'CHARS'/'notadir').read_text(),'preserve')
