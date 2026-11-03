"""AI-drafted negative checks; never launch an app or access an account."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from macos_validate import execute, validate


class InstallerValidationTests(unittest.TestCase):
    def test_wrong_installer_is_rejected_before_any_system_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installer = root / 'wrong.dmg'
            installer.write_bytes(b'synthetic corrupt installer')
            with patch('macos_validate.sys.platform', 'darwin'), patch('macos_validate.platform.machine', return_value='arm64'), patch('macos_validate.execute') as command:
                with self.assertRaisesRegex(AssertionError, 'differs'):
                    validate(installer, root / 'reports', root / 'untouched.app')
            command.assert_not_called()
            result = json.loads((root / 'reports/macos-runtime.json').read_text(encoding='utf-8'))
            self.assertEqual(result['status'], 'failed')
            self.assertFalse(result['neo_hardware_tested'])
            self.assertFalse((root / 'untouched.app').exists())

    def test_nonzero_system_command_cannot_be_reported_as_success(self):
        with patch('macos_validate.subprocess.run') as command:
            command.return_value.returncode = 7
            command.return_value.stderr = 'synthetic launch error'
            with self.assertRaisesRegex(RuntimeError, 'exited 7'):
                execute(['synthetic'])


if __name__ == '__main__':
    unittest.main()
