"""Synthetic archive fixtures; these are NOT real QuickBMS/Steam tests."""
import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
from helpers import Fixture
from engine import digest, describe_game
from safety import BuildError
from preparation import (parse_listing,verify_extraction,stage_preparation,commit_preparation,
                         restore_preparation,validate_manifest,PREP_META)

class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();self.game=self.f.game;self.local=self.f.engine.local
        for name in ('CHARS','STUFF','LEVELS'):shutil.rmtree(self.game/name)
        self.payload={'CHARS/c.txt':'character','STUFF/s.txt':'stuff','LEVELS/l.txt':'level'}
        (self.game/'GAME.DAT').write_text(json.dumps(self.payload))
        self.exe_hash=digest(self.game/'LEGOStarWarsSaga.exe')
    def tearDown(self):self.f.close()
    def extract(self,archive,folder,log):
        folder.mkdir();records={}
        for name,data in json.loads(archive.read_text()).items():
            p=folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data)
            records[name.casefold()]={'path':name,'source':str(p),'bytes':p.stat().st_size,'sha256':digest(p)}
        return records
    def stage(self):return stage_preparation(str(self.game),self.local,lambda _:None,extractor=self.extract)
    def commit(self,**kw):return commit_preparation(self.stage(),self.local,lambda _:None,**kw)
    def test_listing(self):
        r=parse_listing('offset filesize filename\n  00000020  12 CHARS\\BOBA.TXT\n 00000240 4 STUFF/test.txt\n')
        self.assertEqual(r['chars/boba.txt']['bytes'],12)
    def test_list_traversal_rejected(self):
        with self.assertRaises(BuildError):parse_listing('00000020 12 ../bad.txt')
    def test_list_executable_rejected(self):
        with self.assertRaises(BuildError):parse_listing('00000020 12 CHARS/bad.dll')
    def test_list_case_duplicate(self):
        with self.assertRaises(BuildError):parse_listing('00000020 12 CHARS/B.TXT\n00000040 12 chars/b.txt')
    def test_list_warning_rejected(self):
        with self.assertRaises(BuildError):parse_listing('Alert: crc of file not found\n00000020 12 chars/b.txt')
    def test_list_no_rows(self):
        with self.assertRaises(BuildError):parse_listing('Nothing here')
    def test_stage_does_not_modify_game(self):
        p=self.stage();self.assertTrue(p.exists());self.assertTrue((self.game/'GAME.DAT').exists());self.assertFalse((self.game/'CHARS').exists())
    def test_commit_preserves_exe_and_moves_archives(self):
        result=self.commit();self.assertTrue(result['prepared']);self.assertEqual(digest(self.game/'LEGOStarWarsSaga.exe'),self.exe_hash)
        self.assertFalse((self.game/'GAME.DAT').exists());self.assertTrue((self.game/PREP_META/'original-archives'/'GAME.DAT').exists())
        self.assertTrue(describe_game(str(self.game))['prepared_structure'])
    def test_restore_returns_originals(self):
        old=digest(self.game/'GAME.DAT');self.commit();restore_preparation(str(self.game),lambda _:None)
        self.assertEqual(digest(self.game/'GAME.DAT'),old);self.assertFalse((self.game/'CHARS').exists());self.assertFalse((self.game/PREP_META).exists())
    def test_fail_mid_commit_rolls_back(self):
        with self.assertRaises(BuildError):self.commit(fail_after=2)
        self.assertTrue((self.game/'GAME.DAT').exists());self.assertFalse((self.game/'CHARS').exists());self.assertFalse((self.game/PREP_META).exists())
    def test_changed_original_prevents_commit(self):
        m=self.stage();(self.game/'GAME.DAT').write_text('changed')
        with self.assertRaises(BuildError):commit_preparation(m,self.local,lambda _:None)
        self.assertFalse((self.game/PREP_META).exists())
    def test_changed_staging_prevents_commit(self):
        m=self.stage();data=json.loads(m.read_text());Path(data['files'][0]['source']).write_text('changed')
        with self.assertRaises(BuildError):commit_preparation(m,self.local,lambda _:None)
    def test_unknown_existing_mod_is_not_overwritten(self):
        p=self.game/'CHARS/c.txt';p.parent.mkdir();p.write_text('my mod')
        with self.assertRaises(BuildError):self.stage()
        self.assertEqual(p.read_text(),'my mod')
    def test_same_existing_file_preserved_on_restore(self):
        p=self.game/'CHARS/c.txt';p.parent.mkdir();p.write_text('character')
        self.commit();restore_preparation(str(self.game),lambda _:None);self.assertEqual(p.read_text(),'character')
    def test_later_edit_blocks_restore(self):
        self.commit();p=self.game/'CHARS/c.txt';p.write_text('later edit')
        with self.assertRaises(BuildError):restore_preparation(str(self.game),lambda _:None)
        self.assertEqual(p.read_text(),'later edit');self.assertFalse((self.game/'GAME.DAT').exists())
    def test_duplicated_originals_conflict_blocks_before_write(self):
        second=dict(self.payload);second['CHARS/c.txt']='other';(self.game/'GAME1.DAT').write_text(json.dumps(second))
        with self.assertRaises(BuildError):self.stage()
        self.assertTrue((self.game/'GAME.DAT').exists());self.assertTrue((self.game/'GAME1.DAT').exists())
    def test_identical_archive_entries_deduplicate(self):
        (self.game/'GAME1.DAT').write_text(json.dumps(self.payload));result=self.commit();self.assertEqual(result['files'],3)
    def test_nested_bundle_extracted_without_blind_deletion(self):
        payload=dict(self.payload);payload['STUFF/EXTRA.PAK']=json.dumps({'new.txt':'nested'});(self.game/'GAME.DAT').write_text(json.dumps(payload))
        self.commit();self.assertEqual((self.game/'STUFF/new.txt').read_text(),'nested');self.assertFalse((self.game/'STUFF/EXTRA.PAK').exists())
    def test_nested_invalid_bundle_leaves_game_untouched(self):
        payload=dict(self.payload);payload['STUFF/EXTRA.PAK']='not supported';(self.game/'GAME.DAT').write_text(json.dumps(payload))
        with self.assertRaises(ValueError):self.stage()
        self.assertTrue((self.game/'GAME.DAT').exists());self.assertFalse((self.game/PREP_META).exists())
    def test_missing_roots_blocks(self):
        (self.game/'GAME.DAT').write_text(json.dumps({'CHARS/c.txt':'only'}))
        with self.assertRaises(BuildError):self.stage()
    def test_manifest_source_escape_blocks(self):
        m=self.stage();data=json.loads(m.read_text());data['files'][0]['source']=str(self.game/'GAME.DAT');m.write_text(json.dumps(data))
        with self.assertRaises(BuildError):validate_manifest(m,self.local)
    def test_manifest_path_escape_blocks(self):
        m=self.stage();data=json.loads(m.read_text());data['files'][0]['path']='../evil';m.write_text(json.dumps(data))
        with self.assertRaises(BuildError):validate_manifest(m,self.local)
    def test_manifest_archive_path_escape_blocks(self):
        m=self.stage();data=json.loads(m.read_text());data['archives'][0]['name']='../evil.dat';m.write_text(json.dumps(data))
        with self.assertRaises(BuildError):validate_manifest(m,self.local)
    def test_extract_missing_file_blocks(self):
        d=self.f.root/'out';d.mkdir()
        with self.assertRaises(BuildError):verify_extraction(d,{'chars/a.txt':{'path':'CHARS/a.txt','bytes':4}})
    def test_active_mod_journal_prevents_preparation_restore(self):
        self.commit();m=self.game/'.tcs-remaster';m.mkdir();(m/'journal.json').write_text('{}')
        with self.assertRaises(BuildError):restore_preparation(str(self.game),lambda _:None)
