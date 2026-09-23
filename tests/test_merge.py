import unittest
from helpers import BASE
from merge import merge3, decode

class MergeTests(unittest.TestCase):
    def test_identical(self):self.assertEqual(merge3(b'a',b'b',b'b','a.txt').data,b'b')
    def test_left_unchanged(self):self.assertEqual(merge3(b'a',b'a',b'c','a.txt').data,b'c')
    def test_right_unchanged(self):self.assertEqual(merge3(b'a',b'b',b'a','a.txt').data,b'b')
    def test_independent_lines(self):
        r=merge3(b'a\nb\nc\n',b'A\nb\nc\n',b'a\nb\nC\n','a.txt');self.assertTrue(r.ok);self.assertEqual(r.data,b'A\nb\nC\n')
    def test_same_line_conflict(self):self.assertFalse(merge3(b'a\nb\n',b'a\nB\n',b'a\nX\n','a.txt').ok)
    def test_same_insertion_dedup(self):self.assertEqual(merge3(b'a\nc\n',b'a\nb\nc\n',b'a\nb\nc\n','a.txt').data,b'a\nb\nc\n')
    def test_different_insertion_conflict(self):self.assertFalse(merge3(b'a\nc\n',b'a\nb\nc\n',b'a\nx\nc\n','a.txt').ok)
    def test_nonoverlap_deletion(self):
        r=merge3(b'a\nb\nc\nd\n',b'a\nc\nd\n',b'a\nb\nc\nD\n','a.txt');self.assertTrue(r.ok);self.assertEqual(r.data,b'a\nc\nD\n')
    def test_binary_conflict(self):self.assertFalse(merge3(b'\x00a',b'\x00b',b'\x00c','x.gsc').ok)
    def test_fake_text_binary_conflict(self):self.assertFalse(merge3(b'\x00a',b'\x00b',b'\x00c','x.txt').ok)
    def test_encoding_mismatch(self):self.assertFalse(merge3(b'a',b'\xef\xbb\xbfB',b'C','a.txt').ok)
    def test_utf8_bom_kept(self):
        p=b'\xef\xbb\xbf';r=merge3(p+b'a\nb\nc',p+b'A\nb\nc',p+b'a\nb\nC','x.txt');self.assertEqual(r.data,p+b'A\nb\nC')
    def test_crlf_kept(self):
        r=merge3(b'a\r\nb\r\nc',b'A\r\nb\r\nc',b'a\r\nb\r\nC','a.txt');self.assertEqual(r.data,b'A\r\nb\r\nC')
    def test_json_merged_valid(self):
        r=merge3(b'{\n"a":1,\n"b":2\n}',b'{\n"a":3,\n"b":2\n}',b'{\n"a":1,\n"b":4\n}','a.json');self.assertTrue(r.ok)
    def test_unknown_extension_not_merged(self):self.assertFalse(merge3(b'a\nb\nc',b'A\nb\nc',b'a\nb\nC','x.gsc').ok)
    def test_decode_reject_control(self):self.assertIsNone(decode(b'hello\x01'))
