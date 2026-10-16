import tempfile
import unittest
from pathlib import Path
from qa.release_check import inspect

class ReleaseGateTests(unittest.TestCase):
    def test_empty_tree(self):
        with tempfile.TemporaryDirectory() as d:self.assertTrue(inspect(d)['source_scan_pass'])
    def test_private_key_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'x.txt').write_text('-----BEGIN OPENSSH PRIVATE KEY-----')
            self.assertFalse(inspect(d)['source_scan_pass'])
    def test_local_path_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'x.md').write_text('see /Users/someone/Downloads/file')
            self.assertFalse(inspect(d)['source_scan_pass'])
    def test_private_sqlite_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'workspace.sqlite3').write_bytes(b'data')
            self.assertFalse(inspect(d)['source_scan_pass'])
    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'original.txt').write_text('ok');(root/'link.txt').symlink_to('original.txt')
            self.assertFalse(inspect(root)['source_scan_pass'])
    def test_contains_no_publishing_authorisation(self):
        with tempfile.TemporaryDirectory() as d:
            r=inspect(d);self.assertFalse(r['allowed_for_automatic_publication'])
