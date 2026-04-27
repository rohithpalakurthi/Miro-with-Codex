from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TelegramRouterTests(unittest.TestCase):
    def test_muted_message_is_queued_not_sent(self):
        from tools import telegram_router as router

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch.object(router, "CONTROL_FILE", base / "control.json"), \
                 patch.object(router, "HISTORY_FILE", base / "history.json"), \
                 patch.object(router, "DIGEST_FILE", base / "digest.json"), \
                 patch("tools.telegram_router._send_raw") as raw:
                router.save_control({"muted": True})
                result = router.send_message("<b>POSITION MANAGER ONLINE</b>", category="trade")

                self.assertTrue(result["ok"])
                self.assertFalse(result["sent"])
                self.assertTrue(result["muted"])
                raw.assert_not_called()
                self.assertEqual(router.digest_status()["pending_count"], 1)

    def test_command_force_bypasses_mute(self):
        from tools import telegram_router as router

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch.object(router, "CONTROL_FILE", base / "control.json"), \
                 patch.object(router, "HISTORY_FILE", base / "history.json"), \
                 patch.object(router, "DIGEST_FILE", base / "digest.json"), \
                 patch("tools.telegram_router._send_raw", return_value={"ok": True, "sent": True}) as raw:
                router.save_control({"muted": True})
                result = router.send_message("Status reply", category="command", force=True)

                self.assertTrue(result["sent"])
                raw.assert_called_once()
                self.assertEqual(router.digest_status()["pending_count"], 0)


if __name__ == "__main__":
    unittest.main()
