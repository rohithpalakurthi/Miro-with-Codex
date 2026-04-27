from __future__ import annotations

import unittest

from tools.agent_supervisor import status


class AgentSupervisorTests(unittest.TestCase):
    def test_status_shape(self):
        result = status()
        self.assertEqual(result["service"], "launch.py")
        self.assertIn("running", result)
        self.assertIn("state", result)
        self.assertIn("pid_file", result)
        self.assertIn("log_file", result)


if __name__ == "__main__":
    unittest.main()
