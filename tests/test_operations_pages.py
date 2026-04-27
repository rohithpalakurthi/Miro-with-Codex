from __future__ import annotations

import unittest


class OperationsPagesTests(unittest.TestCase):
    def test_new_pages_render(self):
        from agents.master_trader import miro_dashboard_server as server

        client = server.app.test_client()
        for path, marker in [
            ("/operations", "Operations Console"),
            ("/scoreboard", "Paper Trading Scoreboard"),
            ("/strategy-lab", "Strategy Lab"),
            ("/risk-timeline", "Risk Event Timeline"),
        ]:
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(marker, response.get_data(as_text=True))

    def test_navigation_links_are_not_stranded(self):
        from agents.master_trader import miro_dashboard_server as server

        client = server.app.test_client()
        required = ["Operations", "Scoreboard", "Strategy Lab", "Risk Timeline", "Pipeline", "Rules"]
        for path in ["/", "/operations", "/scoreboard", "/strategy-lab", "/risk-timeline", "/pipeline", "/rules", "/legacy"]:
            html = client.get(path).get_data(as_text=True)
            for label in required:
                self.assertIn(label, html, "{} missing {}".format(path, label))

    def test_new_operation_apis_shape(self):
        from agents.master_trader import miro_dashboard_server as server

        client = server.app.test_client()
        for path, key in [
            ("/api/scoreboard", "balance"),
            ("/api/strategy-lab", "promotion"),
            ("/api/ops/audit", "items"),
            ("/api/ops/timeline", "items"),
            ("/api/ops/config-snapshots", "items"),
        ]:
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(key, response.get_json())


if __name__ == "__main__":
    unittest.main()
