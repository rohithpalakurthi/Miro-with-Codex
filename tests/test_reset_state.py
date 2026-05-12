from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tools.reset_state import _backup


class TestResetState(unittest.TestCase):
    def test_backup_copies_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create a source file in a nested directory
            source_dir = tmpdir_path / "subdir"
            source_dir.mkdir()
            source_file = source_dir / "test.json"
            source_file.write_text("{\"key\": \"value\"}")

            backup_root = tmpdir_path / "backups"

            # Note: _backup uses 'target = backup_root / path'
            # If path is relative, it works as expected for this test.
            # We change CWD to tmpdir to simulate the project root.
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                relative_source_path = Path("subdir/test.json")
                _backup(relative_source_path, Path("backups"))

                expected_backup_path = Path("backups/subdir/test.json")
                self.assertTrue(expected_backup_path.exists())
                self.assertEqual(expected_backup_path.read_text(), "{\"key\": \"value\"}")
            finally:
                os.chdir(old_cwd)

    def test_backup_handles_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            backup_root = tmpdir_path / "backups"
            missing_file = tmpdir_path / "ghost.json"

            # Should not raise anything
            _backup(missing_file, backup_root)

            self.assertFalse(backup_root.exists())


if __name__ == "__main__":
    unittest.main()
