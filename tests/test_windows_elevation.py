"""The UAC launcher must explain failure without trying a direct game write."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from helpers import BASE  # Adds app/ to sys.path.
from safety import BuildError
from windows import elevated_action, elevation_failure


class ElevationFailureTests(unittest.TestCase):
    def test_user_cancel_is_distinct_from_launch_failure(self):
        error=elevation_failure(SimpleNamespace(returncode=1,stdout=b'launch-win32:1223\n'))
        self.assertIn('abgebrochen',str(error))
        error=elevation_failure(SimpleNamespace(returncode=1,stdout=b'launch-win32:5\n'))
        self.assertIn('STARTEN.cmd',str(error))
        self.assertIn('Fehler 5',str(error))

    def test_untrusted_shell_output_is_not_reflected(self):
        error=elevation_failure(SimpleNamespace(returncode=3,stdout=b'secret path or shell output'))
        self.assertNotIn('secret',str(error))
        self.assertIn('Exitcode 3',str(error))

    def test_launch_failure_cleans_request_without_fallback(self):
        with tempfile.TemporaryDirectory() as name:
            base=Path(name)
            (base/'.local').mkdir()
            with patch('windows.require_windows'), patch('windows._powershell_process',
                return_value=SimpleNamespace(returncode=1,stdout=b'launch-win32:5\n')):
                with self.assertRaisesRegex(BuildError,'Fehler 5'):
                    elevated_action(base,'install',{'plan_id':'a'*32,'sha256':'b'*64})
            self.assertEqual(list((base/'.local'/'elevated').iterdir()),[])
