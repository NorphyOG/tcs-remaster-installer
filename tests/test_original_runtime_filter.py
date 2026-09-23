"""0.3.2 regression: DLLs in ORIGINAL DAT listings are omitted, not authorised.
All archive content here is synthetic. The subprocess test executes a Python
archiver fixture, NOT QuickBMS and NOT a commercial game binary.
"""
from __future__ import annotations
import fnmatch
import json
import os
import shutil
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
from helpers import Fixture
from engine import Engine, digest, jsonwrite
from safety import BLOCKED, BuildError, Source
from preparation import (ExtractedFiles, ORIGINAL_DATA_POLICY, parse_listing,
    data_extraction_filter, extract_one, verify_extraction, stage_preparation,
    commit_preparation, restore_preparation, validate_manifest)
from nettools import run_process as real_run_process

QUIET = lambda _: None
DATA = {'CHARS/BOBA/BOBA.TXT': 'boba=classic\n',
        'STUFF/ICONS_PC.GSC': 'synthetic-icons',
        'LEVELS/TEST/TEST.TXT': 'synthetic-level'}
PROGRAMS = {'BINKW32.DLL': 'MZ-archived-runtime-must-not-be-installed',
            'LEGOStarWarsSaga.exe': 'MZ-archived-exe-must-not-be-installed',
            'SETUP.BAT': 'not a game asset'}


def make_listing(payload):
    return 'offset filesize filename\n' + '\n'.join(
        f'  {32+i*512:08x} {len(value.encode()):12d} {name}'
        for i, (name, value) in enumerate(payload.items())) + '\n'


def filter_matches(name, rules):
    """Independent simulator of the documented include/exclude filter contract."""
    rules = [r.replace('{}', '*') for r in rules.split(';')]
    positive = [r for r in rules if not r.startswith('!')]
    negative = [r[1:] for r in rules if r.startswith('!')]
    return (any(fnmatch.fnmatchcase(name.casefold(), r.casefold()) for r in positive)
            and not any(fnmatch.fnmatchcase(name.casefold(), r.casefold()) for r in negative))


class SimulatedQuickBMS:
    """Records real production command arguments; reads JSON fixtures only."""
    def __init__(self, ignore_filter=False, injected=None):
        self.calls = []; self.ignore_filter = ignore_filter; self.injected = injected
    def __call__(self, args, *, cwd, timeout, log_file, log):
        self.calls.append(args)
        payload = json.loads(Path(args[-2]).read_text(encoding='utf-8'))
        if '-l' in args:
            log_file.write_text(make_listing(payload), encoding='utf-8'); return
        rule = args[args.index('-f')+1]
        selected = {k: v for k, v in payload.items() if self.ignore_filter or filter_matches(k, rule)}
        if self.injected: selected.update(self.injected)
        for name, value in selected.items():
            p = Path(args[-1])/name.replace('\\', '/')
            p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(value.encode())
        log_file.write_text(make_listing(selected), encoding='utf-8')


class OriginalListingTests(unittest.TestCase):
    def test_exact_031_error_still_reproducible_in_strict_mode(self):
        with self.assertRaisesRegex(BuildError, 'Ausführbare oder administrative Datei im Datenarchiv: BINKW32.DLL'):
            parse_listing(make_listing({**PROGRAMS, **DATA}))
    def test_original_mode_omits_bink_and_keeps_game_assets(self):
        omitted = []
        result = parse_listing(make_listing({**PROGRAMS, **DATA}), original_data=True, excluded=omitted)
        self.assertEqual(set(result), {x.casefold() for x in DATA})
        self.assertEqual({r['path'] for r in omitted}, set(PROGRAMS))
    def test_all_blocked_suffixes_remain_excluded_case_insensitively(self):
        for ext in BLOCKED:
            with self.subTest(ext=ext):
                name = 'CHARS/Tools/IGNORE' + ext.upper()
                excluded = []
                got = parse_listing(make_listing({name: 'x', **DATA}), original_data=True, excluded=excluded)
                self.assertNotIn(name.casefold(), got); self.assertEqual(excluded[0]['path'], name)
    def test_filter_covers_every_blocked_type_and_accepts_data(self):
        rules = data_extraction_filter()
        for ext in BLOCKED:
            self.assertFalse(filter_matches('Nested/Test' + ext.upper(), rules), ext)
        for name in DATA: self.assertTrue(filter_matches(name, rules), name)
        self.assertTrue(filter_matches('MOVIES/BINKW32.DLL.BIK', rules))
    def test_excluded_traversal_is_not_ignored(self):
        for name in ('../BINKW32.DLL', 'STUFF/../../bad.exe', 'C:\\bad.dll', '/tmp/x.dll'):
            with self.subTest(name=name), self.assertRaises(BuildError):
                parse_listing(make_listing({name: 'x', **DATA}), original_data=True)
    def test_unsafe_windows_paths_not_rescued_by_dll(self):
        for name in ('BINKW32.DLL:stream', 'CON.DLL', 'BINKW32.DLL ', 'foo//bad.dll'):
            with self.subTest(name=name), self.assertRaises(BuildError):
                # trailing spaces are trimmed by the QuickBMS row regex; directly
                # test a directory segment for this Windows edge case.
                name = 'bad /x.dll' if name.endswith(' ') else name
                parse_listing(make_listing({name: 'x', **DATA}), original_data=True)
    def test_dot_admin_paths_block_even_inside_game_tree(self):
        for name in ('.local/x.dll', '.tcs-preparation/x.txt', 'STUFF/.git/config'):
            with self.subTest(name=name), self.assertRaises(BuildError):
                parse_listing(make_listing({name: 'x', **DATA}), original_data=True)
    def test_duplicate_excluded_paths_block(self):
        with self.assertRaises(BuildError):
            parse_listing('00000020 1 BINKW32.DLL\n00000040 1 binkw32.dll', original_data=True)
    def test_excluded_path_directory_collision_blocks(self):
        with self.assertRaises(BuildError):
            parse_listing('00000020 1 BINKW32.DLL\n00000040 1 BINKW32.DLL/a.txt', original_data=True)
    def test_excluded_files_still_count_towards_file_limit(self):
        with patch('preparation.MAX_FILES', 1), self.assertRaises(BuildError):
            parse_listing('00000020 1 BINKW32.DLL\n00000040 1 X.EXE', original_data=True)
    def test_excluded_files_still_count_towards_byte_limit(self):
        with patch('preparation.MAX_BYTES', 1), self.assertRaises(BuildError):
            parse_listing('00000020 2 BINKW32.DLL', original_data=True)
    def test_only_runtime_files_return_an_explicit_empty_data_selection(self):
        omitted = []
        self.assertEqual(parse_listing(make_listing(PROGRAMS), original_data=True, excluded=omitted), {})
        self.assertEqual(len(omitted), 3)
    def test_warning_still_stops_original_mode(self):
        with self.assertRaises(BuildError):
            parse_listing('Alert: CRC not found\n' + make_listing(DATA), original_data=True)
    def test_missing_listing_is_not_reported_as_success(self):
        for value in ('', 'No data', None):
            with self.subTest(value=value), self.assertRaises(BuildError):
                parse_listing(value, original_data=True)
    def test_normal_list_and_original_list_match_without_programs(self):
        self.assertEqual(parse_listing(make_listing(DATA)), parse_listing(make_listing(DATA), original_data=True))


class OriginalExtractionTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture(); self.game = self.f.game; self.local = self.f.engine.local
        for name in ('CHARS', 'STUFF', 'LEVELS'): shutil.rmtree(self.game/name)
        self.archive = self.game/'GAME.DAT'
        self.write_payload({**PROGRAMS, **DATA})
        (self.game/'binkw32.dll').write_bytes(b'MZ-existing-legitimate-runtime-preserve-exactly')
        self.runtime_hash = digest(self.game/'binkw32.dll')
        self.exe_hash = digest(self.game/'LEGOStarWarsSaga.exe')
        self.tool = self.f.root/'fake-quickbms.exe'; self.script = self.f.root/'fake-script.bms'
        self.logs = []; self.sim = SimulatedQuickBMS()
    def tearDown(self): self.f.close()
    def write_payload(self, data): self.archive.write_text(json.dumps(data), encoding='utf-8')
    def extract(self, archive, folder, log): return extract_one(self.tool, self.script, archive, folder, log)
    def stage(self):
        with patch('preparation.run_process', side_effect=self.sim):
            return stage_preparation(str(self.game), self.local, self.logs.append, extractor=self.extract)
    def test_production_extract_commands_omit_programs_before_writing(self):
        with patch('preparation.run_process', side_effect=self.sim):
            got = self.extract(self.archive, self.f.root/'out', self.logs.append)
        self.assertEqual(set(got), {x.casefold() for x in DATA})
        self.assertEqual(len(got.excluded), 3)
        self.assertFalse((self.f.root/'out/BINKW32.DLL').exists())
        self.assertIn('BINKW32.DLL', '\n'.join(self.logs))
        command = self.sim.calls[1]
        self.assertIn('-f', command)
        for unsafe in ('-Y', '-C', '-n', '-p', '-w', '-S', '-r'): self.assertNotIn(unsafe, command)
        self.assertNotIn('-f', self.sim.calls[0])  # listing must cover ALL entries
    def test_filter_ignored_by_tool_stops_before_install(self):
        self.sim.ignore_filter = True
        with self.assertRaisesRegex(BuildError, 'trotz Ausschluss'): self.stage()
        self.assertTrue(self.archive.is_file()); self.assertFalse((self.game/'CHARS').exists())
        self.assertEqual(self.runtime_hash, digest(self.game/'binkw32.dll'))
    def test_unlisted_data_from_tool_is_not_silently_installed(self):
        self.sim.injected = {'STUFF/unlisted.txt': 'x'}
        with self.assertRaisesRegex(BuildError, 'weicht'): self.stage()
        self.assertTrue(self.archive.exists())
    def test_existing_runtime_and_exe_survive_commit_and_restore(self):
        original = digest(self.archive); manifest = self.stage()
        record = json.loads(manifest.read_text())
        self.assertEqual(len(record['excluded_original_files']), 3)
        self.assertFalse(any(Path(r['path']).suffix.lower() in BLOCKED for r in record['files']))
        result = commit_preparation(manifest, self.local, QUIET)
        self.assertEqual(result['excluded_original_count'], 3)
        self.assertEqual(self.runtime_hash, digest(self.game/'binkw32.dll'))
        self.assertEqual(self.exe_hash, digest(self.game/'LEGOStarWarsSaga.exe'))
        self.assertFalse((self.game/'SETUP.BAT').exists())
        restore_preparation(str(self.game), QUIET)
        self.assertEqual(original, digest(self.archive))
        self.assertEqual(self.runtime_hash, digest(self.game/'binkw32.dll'))
        self.assertEqual(self.exe_hash, digest(self.game/'LEGOStarWarsSaga.exe'))
    def test_missing_runtime_is_not_created_from_archive(self):
        (self.game/'binkw32.dll').unlink()
        commit_preparation(self.stage(), self.local, QUIET)
        self.assertFalse((self.game/'BINKW32.DLL').exists()); self.assertFalse((self.game/'binkw32.dll').exists())
    def test_nested_program_files_are_also_excluded(self):
        nested = {'local.txt': 'data', 'nested_runtime.DlL': 'MZ-ignore'}
        self.write_payload({**DATA, **PROGRAMS, 'STUFF/EXTRA.PAK': json.dumps(nested)})
        manifest = self.stage(); data = json.loads(manifest.read_text())
        self.assertEqual(len(data['excluded_original_files']), 4)
        commit_preparation(manifest, self.local, QUIET)
        self.assertEqual((self.game/'STUFF/local.txt').read_text(), 'data')
        self.assertFalse((self.game/'STUFF/nested_runtime.DlL').exists())
    def test_runtime_only_secondary_archive_does_not_block_game_data(self):
        (self.game/'GAME1.DAT').write_text(json.dumps({'SECOND.DLL': 'MZ'}))
        manifest = self.stage()
        self.assertEqual(len(json.loads(manifest.read_text())['excluded_original_files']), 4)
        self.assertEqual(len(self.sim.calls), 3)  # GAME1 list only; no extraction
    def test_runtime_only_game_is_not_marked_prepared(self):
        self.write_payload(PROGRAMS)
        with self.assertRaisesRegex(BuildError, 'CHARS, STUFF und LEVELS'): self.stage()
        self.assertEqual(len(self.sim.calls), 1)
    def test_partial_old_031_folder_is_rebuilt_without_touching_downloads(self):
        with patch('preparation.run_process', side_effect=self.sim), \
                patch('preparation.parse_listing', side_effect=BuildError('old 0.3.1 BINKW32.DLL failure')):
            with self.assertRaises(BuildError):
                stage_preparation(str(self.game), self.local, QUIET, extractor=self.extract)
        (self.local/'keep-download.zip').write_bytes(b'private')
        got = self.stage()
        self.assertTrue(got.is_file()); self.assertEqual((self.local/'keep-download.zip').read_bytes(), b'private')
    def test_extraction_audit_survives_verified_cache_resume(self):
        manifest = self.stage(); manifest.unlink(); self.sim.calls.clear()
        got = self.stage()
        self.assertEqual(self.sim.calls, [])
        self.assertEqual(len(json.loads(got.read_text())['excluded_original_files']), 3)
    def test_complete_manifest_can_be_reused_without_new_extraction(self):
        first = self.stage(); self.sim.calls.clear(); second = self.stage()
        self.assertEqual(first, second); self.assertEqual(self.sim.calls, [])
    def test_031_data_only_receipt_remains_compatible(self):
        self.write_payload(DATA); manifest = self.stage(); manifest.unlink()
        for receipt in manifest.parent.glob('*-verified.json'):
            data = json.loads(receipt.read_text()); data.pop('policy'); data.pop('excluded')
            receipt.write_text(json.dumps(data))
        self.sim.calls.clear(); self.stage(); self.assertEqual(self.sim.calls, [])
    def test_tampered_cache_cannot_insert_runtime(self):
        manifest = self.stage(); manifest.unlink()
        receipt = manifest.parent/'archive-00-verified.json'; data = json.loads(receipt.read_text())
        target = manifest.parent/'archive-00/INJECT.DLL'; target.write_bytes(b'MZ-injected')
        data['files']['inject.dll'] = {'path':'INJECT.DLL', 'source':str(target), 'bytes':target.stat().st_size, 'sha256':digest(target)}
        receipt.write_text(json.dumps(data)); self.sim.calls.clear()
        fresh = self.stage()
        self.assertEqual(len(self.sim.calls), 2); self.assertFalse(target.exists())
        self.assertFalse(any(Path(r['path']).suffix.lower() in BLOCKED for r in json.loads(fresh.read_text())['files']))
    def test_manifest_cannot_be_modified_to_install_runtime(self):
        manifest = self.stage(); data = json.loads(manifest.read_text()); data['files'][0]['path'] = 'BINKW32.DLL'
        manifest.write_text(json.dumps(data))
        with self.assertRaises(BuildError): validate_manifest(manifest, self.local)
        self.assertEqual(self.runtime_hash, digest(self.game/'binkw32.dll'))
    def test_injected_commit_failure_restores_original_dat_and_keeps_runtime(self):
        old = digest(self.archive)
        with self.assertRaises(BuildError): commit_preparation(self.stage(), self.local, QUIET, fail_after=2)
        self.assertEqual(old, digest(self.archive)); self.assertFalse((self.game/'CHARS').exists())
        self.assertEqual(self.runtime_hash, digest(self.game/'binkw32.dll'))
    def test_mod_package_dll_remains_blocked(self):
        mod = self.f.root/'mod.zip'
        with zipfile.ZipFile(mod, 'w') as z:
            z.writestr('CHARS/BINKW32.DLL', 'MZ'); z.writestr('CHARS/BOBA.TXT', 'data')
        with Source(mod) as src, self.assertRaisesRegex(BuildError, 'Ausführbare Datei im Datenmod'):
            src.selected('')
    def test_malfunctioning_extractor_cannot_bypass_last_manifest_guard(self):
        def bad(archive, folder, log):
            folder.mkdir(); p = folder/'BINKW32.DLL'; p.write_bytes(b'MZ')
            return {'binkw32.dll': {'path':'BINKW32.DLL','source':str(p),'sha256':digest(p),'bytes':2}}
        with self.assertRaisesRegex(BuildError, 'Programmdatei'):
            stage_preparation(str(self.game), self.local, QUIET, extractor=bad)
    def test_real_child_process_transport_with_synthetic_archiver(self):
        # Exercises stdout capture/CLI arguments/exit code/path quoting for real.
        # NOT a claim about QuickBMS compatibility: fixture uses JSON, not real DAT.
        fake = self.f.root/'synthetic archiver.py'
        fake.write_text('''import fnmatch,json,pathlib,sys
args=sys.argv[1:]; payload=json.loads(pathlib.Path(args[-2]).read_text())
if '-l' not in args:
 rules=args[args.index('-f')+1].replace('{}','*').split(';')
 payload={k:v for k,v in payload.items() if not any(fnmatch.fnmatchcase(k.casefold(),r[1:].casefold()) for r in rules if r.startswith('!'))}
 for k,v in payload.items():
  p=pathlib.Path(args[-1])/k;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v.encode())
print('offset filesize filename')
for i,(k,v) in enumerate(payload.items()): print(f'{i*1024+32:08x} {len(v.encode())} {k}')
''', encoding='utf-8')
        def transport(args, **kw): return real_run_process([sys.executable, str(fake), *args[1:]], **kw)
        with patch('preparation.run_process', side_effect=transport):
            records = self.extract(self.archive, self.f.root/'output with spaces', self.logs.append)
        self.assertEqual(set(records), {x.casefold() for x in DATA})
        self.assertEqual(len(records.excluded), 3)
        self.assertFalse((self.f.root/'output with spaces/BINKW32.DLL').exists())

    def test_full_automatic_mod_install_and_rollback_with_runtime_in_original_dat(self):
        from server import App
        app = App(self.f.base); w = app.workflow; e = app.engine
        e.state['game'] = str(self.game); e.state['options']['clean_target_confirmed'] = True
        w.configure({'allow_tools':True, 'auto_mapping':True, 'desktop_shortcut':False, 'auto_watch':False})
        for mid in ('modern-overhaul','additional-levels-mo','infinities','infinities-al-patch'):
            archive = self.f.root/(mid+'.zip')
            with zipfile.ZipFile(archive, 'w') as z:
                if mid.startswith('infinities'):
                    z.writestr('Common/CHARS/'+mid+'.txt','new')
                    z.writestr('Classic Icons/STUFF/'+mid+'.txt','classic')
                else: z.writestr('Main/LEVELS/'+mid+'.txt','synthetic')
            w.import_data(str(archive), archive.name, QUIET, mid, {'module':mid,'mod_id':next(m['nexus']['mod_id'] for m in e.profile['modules'] if m['id']==mid)})
        self.assertEqual(w.missing(), [])
        original = digest(self.archive)
        def stage(g, local, log, tools=None):
            return stage_preparation(g, local, log, extractor=self.extract)
        with patch('workflow.require_windows'), patch.object(Engine, '_running', return_value=False), \
                patch('workflow.stage_preparation', side_effect=stage), \
                patch('preparation.run_process', side_effect=self.sim):
            result = w.resume(self.logs.append)
            self.assertTrue(result['status'].startswith('INSTALLED'))
            self.assertTrue((self.game/'LEVELS/modern-overhaul.txt').is_file())
            self.assertEqual(digest(self.game/'binkw32.dll'), self.runtime_hash)
            w.restore(str(self.game), False, QUIET); w.restore(str(self.game), True, QUIET)
        self.assertEqual(original, digest(self.archive))
        self.assertEqual(self.runtime_hash, digest(self.game/'binkw32.dll'))
        self.assertEqual(self.exe_hash, digest(self.game/'LEGOStarWarsSaga.exe'))


class OriginalDiagnosticTests(unittest.TestCase):
    def setUp(self):
        from server import App, JobReporter
        self.f = Fixture(); self.app = App(self.f.base); self.reporter = JobReporter(self.app, self.app.job)
    def tearDown(self): self.f.close()
    def test_exclusions_survive_diagnostic_export(self):
        self.reporter.original_filter('GAME.DAT', [{'path':'BINKW32.DLL','bytes':12}])
        got = self.app.diagnostic()['job']['original_filter']
        self.assertEqual(got['excluded_count'], 1); self.assertEqual(got['samples'], ['BINKW32.DLL'])
        self.assertEqual(got['policy'], ORIGINAL_DATA_POLICY)
    def test_bounded_samples_with_exact_total(self):
        self.reporter.original_filter('GAME.DAT', [{'path':f'FILE{i}.DLL','bytes':1} for i in range(40)])
        self.reporter.original_filter('GAME1.DAT', [{'path':'SECOND.DLL','bytes':1}])
        got = self.app.diagnostic()['job']['original_filter']
        self.assertEqual(got['excluded_count'],41); self.assertEqual(got['archives_checked'],2)
        self.assertEqual(len(got['samples']),20)
    def test_empty_originals_still_report_active_filter(self):
        self.reporter.original_filter('GAME.DAT', [])
        self.assertEqual(self.app.diagnostic()['job']['original_filter']['excluded_count'],0)
    def test_private_values_redacted_in_filter_summary(self):
        self.app.workflow.nexus._key = 'fake-private-key'
        self.reporter.original_filter('GAME.DAT', [{'path':'fake-private-key.dll','bytes':1}])
        self.assertNotIn('fake-private-key',json.dumps(self.app.diagnostic()))
