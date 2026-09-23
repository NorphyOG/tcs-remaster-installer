"""0.3.3: binary PAK fixtures, not JSON masquerading as PAK payloads.
The old QuickBMS look-ahead is emulated only to reproduce the numeric failure;
no test here claims to execute the Windows QuickBMS binary or commercial data.
"""
import io
import json
import shutil
import struct
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from helpers import Fixture
from diagnostics import Cancelled
from engine import digest, jsonwrite
from safety import BLOCKED, BuildError
from tt_pak import inspect_pak, extract_raw, patched_deflate_script, HEADER, RECORD
from preparation import extract_one, stage_preparation, commit_preparation, restore_preparation

QUIET = lambda _: None
KASHYYYK = 'LEVELS/NEWBONUS/NB_KASHYYYK/NB_KASHYYYK_A/AI/AI.PAK'
# A minimal synthetic script fixture with the documented routine shape, not a
# redistributed ttgames.bms. Used for patch-contract tests, not BMS execution.
SCRIPT = '''# Traveller's Tales synthetic script fixture
startfunction EXTRACT_FILE
endfunction
startfunction DEFLATE_UNPACK
    getdstring SIGN 0x20
    if SIGN == "Deflate_v1.0"
        comtype dflt
        get XSIZE long
        math OFFSET + 0x24
        math SIZE   - 0x24
        clog NAME OFFSET SIZE XSIZE
    else
        log NAME OFFSET SIZE
    endif
endfunction
'''


def make_pak(files, *, first_offset=None):
    """Independently construct the public 24/28-byte table format."""
    if isinstance(files, dict): files = list(files.items())
    table_size = 24 + 28 * len(files)
    names = bytearray(); name_offsets = []
    for name, _ in files:
        name_offsets.append(table_size + len(names))
        names.extend(name.encode('ascii') + b'\0')
    data_start = table_size + len(names)
    if first_offset is not None:
        if first_offset < data_start: raise ValueError('names too large for specified offset')
        names.extend(b'\0' * (first_offset - data_start)); data_start = first_offset
    payload = bytearray(); records = bytearray()
    for n, (name, value) in enumerate(files):
        records.extend(struct.pack('<7I', name_offsets[n], data_start + len(payload), len(value), 4, 0, 0, 0))
        payload.extend(value)
    total = 24 + len(records) + len(names) + len(payload)
    return struct.pack('<6I', 0x1234567a, len(files), total, 0, 0, 0) + records + names + payload


def user_shape():
    # First 3 offsets and lengths match the user's log. The fourth file's name
    # and all bytes are synthetic; the actual last entry was not provided.
    files = [('ATTACK.SCP', b'A' * 1120), ('LEVEL.SCP', b'L' * 1625),
             ('NB_KASHYYYK_A.AI2', b'N' * 7257), ('TAIL.TXT', b'small=1\r\nEND\r\n')]
    assert len(files[-1][1]) == 14
    files[-1] = ('TAIL.TXT', b'0123456789abc')
    return make_pak(files, first_offset=186), dict(files)


class PakBoundsTests(unittest.TestCase):
    def setUp(self): self.f = Fixture(); self.archive = self.f.root/'AI.PAK'
    def tearDown(self): self.f.close()
    def write(self, data): self.archive.write_bytes(data); return self.archive
    def test_reported_offsets_reproduce_19_byte_shortfall(self):
        data, _ = user_shape(); self.write(data); index = inspect_pak(self.archive)
        self.assertEqual(len(data), 10201)
        self.assertEqual([r.offset for r in index.entries], [0xba, 0x51a, 0xb73, 0x27cc])
        old_read = io.BytesIO(data); old_read.seek(index.entries[-1].offset)
        got = old_read.read(32)
        self.assertEqual(32-len(got), 19); self.assertEqual(old_read.tell(), 0x27d9)
    def test_actual_binary_short_pak_extracts_all_four_files_without_tool(self):
        data, files = user_shape(); self.write(data)
        with patch('preparation.run_process', side_effect=AssertionError('native path must not launch a tool')):
            result = extract_one(None, None, self.archive, self.f.root/'out', QUIET)
        self.assertEqual(len(result), 4)
        for name, value in files.items(): self.assertEqual((self.f.root/'out'/name).read_bytes(), value)
        self.assertEqual(result.format_info['short_entries'], 1)
        self.assertEqual(result.format_info['method'], 'native-raw')
    def test_all_short_lengths_including_zero_are_preserved(self):
        files = {f'entry-{n}.txt': bytes([n])*n for n in range(33)}
        self.write(make_pak(files)); result = extract_one(None, None, self.archive, self.f.root/'out', QUIET)
        self.assertEqual(len(result), 33)
        for name, value in files.items(): self.assertEqual((self.f.root/'out'/name).read_bytes(), value)
    def test_short_not_last_does_not_probe_into_the_next_entry(self):
        self.write(make_pak({'empty.txt': b'', 'one.txt': b'D', 'next.txt': b'eflate_v1.0\0'+b'\0'*30}))
        index = inspect_pak(self.archive)
        self.assertFalse(index.needs_codec)
        self.assertEqual(index.entries[0].output_bytes, 0)
    def test_short_content_resembling_truncated_header_is_rejected(self):
        self.write(make_pak({'short.txt': b'Deflate_v1.0\0'}))
        with self.assertRaisesRegex(BuildError, 'Header'): inspect_pak(self.archive)
    def test_empty_pak_is_explicitly_handled(self):
        self.write(make_pak({})); got = extract_one(None, None, self.archive, self.f.root/'out', QUIET)
        self.assertEqual(got, {}); self.assertEqual(got.format_info['entries'], 0)
    def test_unknown_magic_returns_none_not_false_success(self):
        self.write(b'not a pak'); self.assertIsNone(inspect_pak(self.archive))
    def test_unknown_pak_still_propagates_quickbms_error(self):
        self.write(b'not a pak')
        with patch('preparation.run_process', side_effect=BuildError('Werkzeug meldet Fehlercode 3')):
            with self.assertRaisesRegex(BuildError, 'Fehlercode 3'):
                extract_one(Path('tool'), Path('script'), self.archive, self.f.root/'out', QUIET)
    def test_missing_header_stops(self):
        self.write(b'\x7a\x56\x34\x12')
        with self.assertRaises(BuildError): inspect_pak(self.archive)
    def test_truncated_table_stops(self):
        self.write(struct.pack('<6I', 0x1234567a, 3, 24, 0, 0, 0))
        with self.assertRaises(BuildError): inspect_pak(self.archive)
    def test_count_limit_stops(self):
        self.write(make_pak({'a': b'a', 'b': b'b'}))
        with patch('tt_pak.MAX_FILES', 1), self.assertRaises(BuildError): inspect_pak(self.archive)
    def test_truncated_payload_stops_before_any_file_is_written(self):
        self.write(user_shape()[0][:-1])
        with self.assertRaisesRegex(BuildError, 'Dateibereich'):
            extract_one(None, None, self.archive, self.f.root/'out', QUIET)
        self.assertFalse((self.f.root/'out').exists())
    def test_oversized_entry_stops(self):
        data = bytearray(make_pak({'x': b'x'})); struct.pack_into('<I', data, 24+8, 0xffffffff); self.write(data)
        with self.assertRaises(BuildError): inspect_pak(self.archive)
    def test_payload_offset_into_header_stops(self):
        data = bytearray(make_pak({'x': b'x'})); struct.pack_into('<I', data, 24+4, 4); self.write(data)
        with self.assertRaises(BuildError): inspect_pak(self.archive)
    def test_name_offset_outside_file_stops(self):
        data = bytearray(make_pak({'x': b'x'})); struct.pack_into('<I', data, 24, len(data)); self.write(data)
        with self.assertRaises(BuildError): inspect_pak(self.archive)
    def test_unterminated_name_stops(self):
        data = bytearray(make_pak({'x': b'x'})); data[53] = 120; self.write(data)
        with self.assertRaises(BuildError): inspect_pak(self.archive)
    def test_all_unsafe_paths_remain_blocked_in_binary_pak(self):
        for name in ('../x.dll', 'C:/x.txt', '.local/config', 'STUFF/.git/x', 'CON', 'a//b', '/abs', 'a:stream', 'x '):
            with self.subTest(name=name):
                self.write(make_pak({name: b'x'}))
                with self.assertRaises(BuildError): inspect_pak(self.archive)
    def test_case_collision_blocks(self):
        self.write(make_pak([('a.txt', b'a'), ('A.TXT', b'b')]))
        with self.assertRaises(BuildError): inspect_pak(self.archive)
    def test_file_directory_collision_blocks(self):
        self.write(make_pak({'a': b'a', 'a/b': b'b'}))
        with self.assertRaises(BuildError): inspect_pak(self.archive)
    def test_excluded_runtime_files_still_not_written(self):
        files = {f'ignore{i}{ext}': b'MZ?' for i, ext in enumerate(sorted(BLOCKED))}; files['ok.txt'] = b'ok'
        self.write(make_pak(files)); result = extract_one(None, None, self.archive, self.f.root/'out', QUIET)
        self.assertEqual(set(result), {'ok.txt'}); self.assertEqual(len(result.excluded), len(BLOCKED))
        self.assertEqual(len(list((self.f.root/'out').iterdir())), 1)
    def test_excluded_sizes_count_towards_limit(self):
        self.write(make_pak({'x.dll': b'x' * 100}))
        with patch('tt_pak.MAX_BYTES', 90), self.assertRaises(BuildError): inspect_pak(self.archive)
    def test_compressed_output_size_limit(self):
        header = b'Deflate_v1.0'.ljust(32, b'\0') + struct.pack('<I', 0xffffffff) + b'payload'
        self.write(make_pak({'c.txt': header}))
        with patch('tt_pak.MAX_BYTES', 1000), self.assertRaises(BuildError): inspect_pak(self.archive)
    def test_compressed_entries_are_not_copied_as_raw(self):
        header = b'Deflate_v1.0'.ljust(32, b'\0') + struct.pack('<I', 5) + b'payload'
        self.write(make_pak({'c.txt': header})); index = inspect_pak(self.archive)
        self.assertTrue(index.needs_codec); self.assertEqual(index.entries[0].output_bytes, 5)
        with self.assertRaises(BuildError): extract_raw(index, self.f.root/'out')
    def test_changed_archive_before_copy_is_rejected(self):
        self.write(make_pak({'x': b'data'})); index = inspect_pak(self.archive); self.archive.write_bytes(b'changed')
        with self.assertRaisesRegex(BuildError, 'verändert'): extract_raw(index, self.f.root/'out')
    def test_cancellation_is_not_swallowed(self):
        self.write(make_pak({'x': b'data'})); log = Mock(); log.check_cancelled.side_effect = Cancelled('stop')
        with self.assertRaises(Cancelled): inspect_pak(self.archive, log)
    def test_symlink_target_refused(self):
        self.write(make_pak({'x/file.txt': b'data'})); index = inspect_pak(self.archive)
        out = self.f.root/'out'; out.mkdir(); (out/'x').symlink_to(self.f.game, target_is_directory=True)
        with self.assertRaises(BuildError): extract_raw(index, out)
    def test_bounded_patch_is_narrow_and_preserves_source(self):
        source = self.f.root/'script.bms'; source.write_text(SCRIPT); before = digest(source)
        dest = self.f.root/'bounded.bms'; report = patched_deflate_script(source, dest)
        self.assertEqual(before, digest(source)); self.assertEqual(report['derived_sha256'], digest(dest))
        self.assertIn('getdstring SIGN TCS_PROBE_SIZE', dest.read_text())
        self.assertNotIn('getdstring SIGN 0x20', dest.read_text())
        self.assertIn('SIZE < 0x24', dest.read_text())
    def test_unknown_or_duplicate_routine_is_not_patched(self):
        source = self.f.root/'script.bms'
        for content in (SCRIPT.replace('comtype dflt', 'comtype something_else'), SCRIPT + SCRIPT, ''):
            source.write_text(content)
            with self.assertRaises(BuildError): patched_deflate_script(source, self.f.root/'out.bms')
    def test_unsafe_script_is_not_patched_or_executed(self):
        source = self.f.root/'script.bms'; source.write_text(SCRIPT+'\nexecute bad\n')
        with self.assertRaises(BuildError): patched_deflate_script(source, self.f.root/'out.bms')
    def test_compressed_path_checks_tool_listing_against_native_index(self):
        header = b'Deflate_v1.0'.ljust(32, b'\0') + struct.pack('<I', 5) + b'payload'
        self.write(make_pak({'c.txt': header})); source = self.f.root/'script.bms'; source.write_text(SCRIPT)
        def bad_list(args, **kw): kw['log_file'].write_text('00000040 5 wrong.txt\n')
        with patch('preparation.run_process', side_effect=bad_list), self.assertRaisesRegex(BuildError, 'PAK-Tabelle'):
            extract_one(Path('tool'), source, self.archive, self.f.root/'out', QUIET)
    def test_compressed_correct_listing_and_bounded_arguments(self):
        header = b'Deflate_v1.0'.ljust(32, b'\0') + struct.pack('<I', 5) + b'payload'
        self.write(make_pak({'c.txt': header, 'tiny.txt': b't'}))
        source = self.f.root/'script.bms'; source.write_text(SCRIPT); calls = []
        def codec_simulator(args, **kw):
            calls.append(args); self.assertIn('TCS_PROBE_SIZE', Path(args[-3]).read_text())
            kw['log_file'].write_text('00000060 5 c.txt\n000000a0 1 tiny.txt\n')
            if '-l' not in args:
                (Path(args[-1])/'c.txt').write_bytes(b'12345'); (Path(args[-1])/'tiny.txt').write_bytes(b't')
        with patch('preparation.run_process', side_effect=codec_simulator):
            result = extract_one(Path('tool'), source, self.archive, self.f.root/'out', QUIET)
        self.assertEqual(len(calls), 2); self.assertEqual(result['tiny.txt']['bytes'], 1)
        self.assertEqual(result.format_info['method'], 'quickbms-bounded-dflt')


class PakResumeTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture(); self.game = self.f.game; self.local = self.f.engine.local
        for n in ('CHARS', 'STUFF', 'LEVELS'): shutil.rmtree(self.game/n)
        # Genuine synthetic 0x1234567a bytes as container at GAME.DAT. A real
        # retail outer DAT is still handled by QuickBMS; that isn't tested here.
        self.payload = {'CHARS/boba.txt': b'boba', 'STUFF/stuff.txt': b'stuff',
                        'LEVELS/test.txt': b'level', KASHYYYK: user_shape()[0], 'BINKW32.DLL': b'MZ-unused'}
        self.dat = self.game/'GAME.DAT'; self.dat.write_bytes(make_pak(self.payload))
        self.dll = self.game/'binkw32.dll'; self.dll.write_bytes(b'MZ-existing-runtime')
        self.hashes = digest(self.dat), digest(self.dll), digest(self.game/'LEGOStarWarsSaga.exe')
        self.logs = []
    def tearDown(self): self.f.close()
    def stage(self): return stage_preparation(str(self.game), self.local, self.logs.append)
    def test_complete_native_nested_stage_commit_and_rollback(self):
        with patch('preparation.Tools.quickbms', side_effect=AssertionError('No tool needed for these binary fixtures')):
            manifest = self.stage()
        state = json.loads(manifest.read_text()); self.assertEqual(len(state['archive_checks']), 2)
        self.assertTrue(any(KASHYYYK in r['archive'] for r in state['archive_checks']))
        commit_preparation(manifest, self.local, QUIET)
        tail = self.game/str(Path(KASHYYYK).parent)/'TAIL.TXT'
        self.assertEqual(tail.read_bytes(), b'0123456789abc')
        self.assertEqual(digest(self.dll), self.hashes[1])
        restore_preparation(str(self.game), QUIET)
        self.assertEqual((digest(self.dat), digest(self.dll), digest(self.game/'LEGOStarWarsSaga.exe')), self.hashes)
    def test_resume_032_failed_nested_pak_reuses_outer_receipt(self):
        from preparation import inspect_pak as real_inspect
        def old_fault(path, log=QUIET):
            if path.name == 'AI.PAK': raise BuildError('Werkzeug meldet Fehlercode 3')
            return real_inspect(path, log)
        with patch('preparation.inspect_pak', side_effect=old_fault), self.assertRaises(BuildError): self.stage()
        folders = list((self.local/'preparation').iterdir()); self.assertEqual(len(folders), 1)
        work = folders[0]
        receipt = work/'archive-00-verified.json'; self.assertTrue(receipt.is_file())
        saved = json.loads(receipt.read_text()); saved.pop('format_info', None); jsonwrite(receipt, saved)
        old_receipt_hash = digest(receipt)
        partial = work/'nested-1'; partial.mkdir(exist_ok=True); (partial/'old-partial.txt').write_bytes(b'partial')
        marker = self.local/'retained-mod.zip'; marker.write_bytes(b'download-marker')
        got = self.stage()
        self.assertTrue(got.is_file()); self.assertEqual(digest(receipt), old_receipt_hash)
        self.assertEqual(marker.read_bytes(), b'download-marker'); self.assertFalse((partial/'old-partial.txt').exists())
        self.assertIn('Geprüfter Teilschritt wiederverwendet: GAME.DAT', '\n'.join(self.logs))
    def test_complete_stage_reuses_without_quickbms_download(self):
        first = self.stage()
        with patch('preparation.Tools.quickbms', side_effect=AssertionError('No redownload')):
            second = self.stage()
        self.assertEqual(first, second)
    def test_partial_stage_reuses_all_verified_binary_files(self):
        first = self.stage(); first.unlink()
        with patch('preparation.Tools.quickbms', side_effect=AssertionError('No redownload')), \
                patch('preparation.extract_raw', side_effect=AssertionError('No re-extraction')):
            self.stage()
    def test_truncated_nested_pak_does_not_touch_originals(self):
        self.payload[KASHYYYK] = user_shape()[0][:-1]; self.dat.write_bytes(make_pak(self.payload)); before = digest(self.dat)
        with self.assertRaises(BuildError): self.stage()
        self.assertEqual(digest(self.dat), before); self.assertEqual(digest(self.dll), self.hashes[1])
        self.assertFalse((self.game/'CHARS').exists())
    def test_later_user_changes_remain_protected_by_restore(self):
        commit_preparation(self.stage(), self.local, QUIET)
        tail = self.game/str(Path(KASHYYYK).parent)/'TAIL.TXT'; tail.write_bytes(b'user changed')
        with self.assertRaises(BuildError): restore_preparation(str(self.game), QUIET)
        self.assertEqual(tail.read_bytes(), b'user changed')
