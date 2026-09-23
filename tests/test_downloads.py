"""Mocked HTTPS / Nexus contracts; no account credentials or network required."""
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from helpers import Fixture
from safety import BuildError
from nettools import allowed_url,download,Redirects,QUICKBMS_SHA256
from nexus import parse_nxm,Nexus,DownloadWatch

class Response(io.BytesIO):
    def __init__(self,data,headers=None):super().__init__(data);self.headers=headers or {'Content-Length':str(len(data))}

class DownloadTests(unittest.TestCase):
    def test_allowed_https(self):self.assertIn('api.nexusmods',allowed_url('https://api.nexusmods.com/v1/users/validate.json','api'))
    def test_reject_http(self):
        with self.assertRaises(BuildError):allowed_url('http://api.nexusmods.com/x','api')
    def test_reject_loopback(self):
        with self.assertRaises(BuildError):allowed_url('https://127.0.0.1/a','mod')
    def test_reject_fake_nexus_suffix(self):
        with self.assertRaises(BuildError):allowed_url('https://nexusmods.com.evil.example/a','mod')
    def test_api_host_only(self):
        with self.assertRaises(BuildError):allowed_url('https://cf-files.nexusmods.com/a','api')
    def test_allowed_cdn(self):self.assertTrue(allowed_url('https://cf-files.nexusmods.com/a?token=secret','mod'))
    def test_reject_url_credentials(self):
        with self.assertRaises(BuildError):allowed_url('https://user:secret@api.nexusmods.com/x','api')
    def test_reject_nonstandard_port(self):
        with self.assertRaises(BuildError):allowed_url('https://api.nexusmods.com:8443/x','api')
    def test_hash_checked_download(self):
        with tempfile.TemporaryDirectory() as d,patch('nettools.open_url',return_value=Response(b'abc')):
            p=Path(d)/'a.zip';r=download('https://github.com/a',p,expected_sha256=hashlib.sha256(b'abc').hexdigest())
            self.assertTrue(r['hash_verified']);self.assertEqual(p.read_bytes(),b'abc')
    def test_wrong_hash_removes_partial(self):
        with tempfile.TemporaryDirectory() as d,patch('nettools.open_url',return_value=Response(b'abc')):
            p=Path(d)/'a.zip'
            with self.assertRaises(BuildError):download('https://github.com/a',p,expected_sha256='0'*64)
            self.assertEqual(list(Path(d).iterdir()),[])
    def test_size_limit(self):
        with tempfile.TemporaryDirectory() as d,patch('nettools.open_url',return_value=Response(b'abc')):
            with self.assertRaises(BuildError):download('https://github.com/a',Path(d)/'a.zip',maximum=2)
    def test_truncated_download(self):
        with tempfile.TemporaryDirectory() as d,patch('nettools.open_url',return_value=Response(b'abc',{'Content-Length':'10'})):
            with self.assertRaises(BuildError):download('https://github.com/a',Path(d)/'a.zip')
    def test_existing_target_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.zip';p.write_bytes(b'old')
            with self.assertRaises(BuildError):download('https://github.com/a',p)
            self.assertEqual(p.read_bytes(),b'old')
    def test_quickbms_hash_pinned(self):self.assertRegex(QUICKBMS_SHA256,r'^[0-9a-f]{64}$')

class NxmTests(unittest.TestCase):
    def base(self,query=''):return 'nxm://legostarwarsthecompletesaga/mods/54/files/583'+query
    def test_unsigned_nxm(self):self.assertEqual(parse_nxm(self.base(),{54})['file_id'],583)
    def test_signed_nxm(self):self.assertEqual(parse_nxm(self.base('?key=Ab_cd-1&expires=200&user_id=3'),{54},now=100)['user_id'],3)
    def test_wrong_game(self):
        with self.assertRaises(BuildError):parse_nxm('nxm://skyrim/mods/54/files/583',{54})
    def test_wrong_mod(self):
        with self.assertRaises(BuildError):parse_nxm(self.base(),{133})
    def test_expired(self):
        with self.assertRaises(BuildError):parse_nxm(self.base('?key=x&expires=99'),{54},now=100)
    def test_duplicate_query(self):
        with self.assertRaises(BuildError):parse_nxm(self.base('?key=x&key=y&expires=200'),{54},now=100)
    def test_missing_expiry(self):
        with self.assertRaises(BuildError):parse_nxm(self.base('?key=x'),{54})
    def test_unknown_query(self):
        with self.assertRaises(BuildError):parse_nxm(self.base('?execute=evil.exe'),{54})
    def test_fragment(self):
        with self.assertRaises(BuildError):parse_nxm(self.base('#x'),{54})

class NexusTests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.n=Nexus(self.f.engine.profile,self.f.engine.local)
    def tearDown(self):self.f.close()
    def test_key_not_public_or_persisted(self):
        with patch.object(self.n,'api',return_value={'user_id':3,'name':'tester','is_premium':False,'email':'private'}):self.n.connect('mySecretKey123')
        self.assertNotIn('mySecretKey123',json.dumps(self.n.status()));self.assertNotIn('email',self.n._user)
        self.assertFalse(any('mySecretKey123' in p.read_text(errors='ignore') for p in self.f.engine.local.rglob('*.json')))
    def test_invalid_auth_clears_key(self):
        with patch.object(self.n,'api',side_effect=BuildError('invalid')):
            with self.assertRaises(BuildError):self.n.connect('mySecretKey123')
        self.assertFalse(self.n.status()['connected'])
    def test_disconnect_forgets_key(self):
        self.n._key='secret';self.n.disconnect();self.assertIsNone(self.n._key)
    def test_free_direct_download_not_attempted(self):
        self.n._key='secret';self.n._user={'user_id':3,'is_premium':False};self.n.catalog={'x':{'mod_id':54,'file_id':583}}
        with patch.object(self.n,'api') as api:
            with self.assertRaises(BuildError):self.n.fetch('x',lambda _:None)
            api.assert_not_called()
    def test_old_versions_not_selected(self):
        with patch.object(self.n,'api',return_value={'files':[{'file_id':583,'category_id':4,'name':'Lego Star Wars The Complete Saga Modern Overhaul','version':'2.2.2','file_name':'x.zip'}]}):
            r=self.n.resolve(lambda _:None)
        self.assertEqual(r['files'],[])
    def test_exact_pinned_file_resolved(self):
        with patch.object(self.n,'api',return_value={'files':[{'file_id':583,'category_id':1,'name':'Lego Star Wars The Complete Saga Modern Overhaul','version':'2.2.2','file_name':'x.zip'}]}):r=self.n.resolve(lambda _:None)
        self.assertEqual(r['files'][0]['file_id'],583)
    def test_changed_version_blocks_resolution(self):
        with patch.object(self.n,'api',return_value={'files':[{'file_id':583,'category_id':1,'name':'Lego Star Wars The Complete Saga Modern Overhaul','version':'9.0','file_name':'x.zip'}]}):r=self.n.resolve(lambda _:None)
        self.assertEqual(r['files'],[])

class WatchTests(unittest.TestCase):
    def setUp(self):self.f=Fixture();self.w=DownloadWatch(self.f.engine.profile);self.folder=self.f.root/'downloads';self.folder.mkdir()
    def tearDown(self):self.f.close()
    def test_waits_for_stability(self):
        (self.folder/'Additional Levels Modern Overhaul-32.zip').write_bytes(b'a')
        self.assertEqual(self.w.candidates(str(self.folder),now=0),[]);self.assertEqual(self.w.candidates(str(self.folder),now=7),[])
        self.assertEqual(len(self.w.candidates(str(self.folder),now=9)),1)
    def test_ignores_unrelated(self):
        (self.folder/'private-bank-documents.zip').write_bytes(b'a');self.w.candidates(str(self.folder),now=0);self.assertEqual(self.w.candidates(str(self.folder),now=10),[])
    def test_ignores_incomplete(self):
        (self.folder/'Refinement Overhaul.zip.crdownload').write_bytes(b'a');self.w.candidates(str(self.folder),now=0);self.assertEqual(self.w.candidates(str(self.folder),now=10),[])
    def test_same_file_imported_once(self):
        (self.folder/'Refinement Overhaul.zip').write_bytes(b'a');self.w.candidates(str(self.folder),now=0)
        c=self.w.candidates(str(self.folder),now=10)[0];self.w.mark_done(c);self.assertEqual(self.w.candidates(str(self.folder),now=20),[])
    def test_changes_reset_stability(self):
        p=self.folder/'Refinement Overhaul.zip';p.write_bytes(b'a');self.w.candidates(str(self.folder),now=0);p.write_bytes(b'longer');self.assertEqual(self.w.candidates(str(self.folder),now=10),[])

class ScriptPolicyTests(unittest.TestCase):
    def checked(self, suffix):
        from nettools import validate_script
        return validate_script("# Traveller's Tales\nstartfunction EXTRACT_FILE\n"+suffix)
    def test_parser_only_script_allowed(self):self.checked('get SIZE long\n')
    def test_missing_script_identity_rejected(self):
        from nettools import validate_script
        with self.assertRaises(BuildError):validate_script('get SIZE long\n')
    def test_calldll_rejected(self):
        with self.assertRaises(BuildError):self.checked('  CallDLL x.dll y cdecl RET\n')
    def test_comtype_execute_rejected(self):
        with self.assertRaises(BuildError):self.checked('ComType "EXECUTE" "cmd"\n')
    def test_encryption_execute_rejected(self):
        with self.assertRaises(BuildError):self.checked('encryption execute "cmd"\n')
