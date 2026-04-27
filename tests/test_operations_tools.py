from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class OperationsToolsTests(unittest.TestCase):
    def test_live_lock_defaults_locked_and_unlocks(self):
        import tools.live_mode_lock as lock

        with tempfile.TemporaryDirectory() as tmpdir:
            old = lock.LOCK_FILE
            try:
                lock.LOCK_FILE = Path(tmpdir) / "live_mode_lock.json"
                self.assertFalse(lock.status().get("unlocked"))
                self.assertTrue(lock.unlock(actor="test", minutes=1).get("unlocked"))
                self.assertFalse(lock.lock("test lock").get("unlocked"))
            finally:
                lock.LOCK_FILE = old

    def test_watchdog_check_shape_without_recovery(self):
        from tools.watchdog import check_once

        result = check_once(auto_recover=False)
        self.assertIn("health_status", result)
        self.assertIn("agent_process", result)
        self.assertFalse(result["auto_recover"])


if __name__ == "__main__":
    unittest.main()
