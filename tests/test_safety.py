import io, os, stat, tempfile, unittest, zipfile
from pathlib import Path
from helpers import BASE
from safety import BuildError, Source, safe_rel, checked_entries, no_links

class SafetyTests(unittest.TestCase):
    def test_valid_unicode_path(self): self.assertEqual(safe_rel('CHARS/Öbi_Wan/file.txt'),'CHARS/Öbi_Wan/file.txt')
    def test_windows_separators(self): self.assertEqual(safe_rel(r'CHARS\boba\file.txt'),'CHARS/boba/file.txt')
    def test_bad_paths(self):
        for p in ['../evil','/etc/evil','C:/evil','a/../../b','a//b','AUX.txt','chars/NUL','a.txt:evil','con/foo','COM¹.txt','a./b','a /b','a\x00b','a/./b','a/<b','a/'+('b'*221)]:
            with self.subTest(p=p),self.assertRaises(BuildError): safe_rel(p)
    def test_case_collision(self):
        with self.assertRaises(BuildError): checked_entries(['CHARS/A.txt','chars/a.TXT'])
    def test_file_directory_collision(self):
        with self.assertRaises(BuildError): checked_entries(['CHARS/a','CHARS/a/b.txt'])
    def z(self,td,names):
        p=Path(td)/'test.zip'
        with zipfile.ZipFile(p,'w') as z:
            for n,v in names.items():z.writestr(n,v)
        return p
    def test_zip_roots_and_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            p=self.z(td,{'Wrapper/CHARS/a.txt':'a','Wrapper/readme.txt':'readme','Wrapper/Classic/STUFF/a.gsc':'x','Wrapper/MO Icons/STUFF/a.gsc':'y'})
            with Source(p) as s:
                self.assertEqual(set(s.roots()),{'Wrapper','Wrapper/Classic','Wrapper/MO Icons'})
                self.assertEqual([r for r,_ in s.selected('Wrapper')],['CHARS/a.txt'])
    def test_zip_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=self.z(td,{'../bad':'bad'})
            with self.assertRaises(BuildError):Source(p)
    def test_zip_case_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=self.z(td,{'CHARS/A.txt':'a','chars/a.txt':'b'})
            with self.assertRaises(BuildError):Source(p)
    def test_archive_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'test.zip'
            with zipfile.ZipFile(p,'w') as z:
                info=zipfile.ZipInfo('CHARS/link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'/tmp')
            with self.assertRaises(BuildError):Source(p)
    def test_executable_assets_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=self.z(td,{'CHARS/plugin.dll':b'MZ'})
            with Source(p) as s,self.assertRaises(BuildError):s.selected('')
    def test_root_executable_not_copied(self):
        with tempfile.TemporaryDirectory() as td:
            p=self.z(td,{'CHARS/a.txt':'a','setup.exe':b'MZ','ModConfig.json':'{}'})
            with Source(p) as s:self.assertEqual(len(s.selected('')),1)
    def test_copy_hash(self):
        with tempfile.TemporaryDirectory() as td:
            p=self.z(td,{'CHARS/a.txt':'hello'})
            with Source(p) as s:
                out=Path(td)/'out'
                sha=s.copy(s.entries[0],out)
                self.assertEqual(out.read_bytes(),b'hello');self.assertEqual(len(sha),64)
    def test_folder_no_links(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'real').mkdir()
            try:(p/'link').symlink_to(p/'real',target_is_directory=True)
            except OSError:self.skipTest('OS does not allow symlink creation')
            with self.assertRaises(BuildError):no_links(p/'link'/'file')
    def test_unknown_root_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=self.z(td,{'CHARS/a.txt':'a'})
            with Source(p) as s,self.assertRaises(BuildError):s.selected('fake')
