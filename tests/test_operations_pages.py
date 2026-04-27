from __future__ import annotations

import unittest


class OperationsPagesTests(unittest.TestCase):
    def test_new_pages_render(self):
        from agents.master_trader import miro_dashboard_server as server

        client = server.app.test_client()
        for path, marker in [
            ("/autonomy-suite", "Autonomy Suite"),
            ("/risk-cockpit", "Risk Cockpit"),
            ("/trade-journal", "Trade Decision Journal"),
            ("/operations", "Operations Console"),
            ("/scoreboard", "Paper Trading Scoreboard"),
            ("/strategy-lab", "Strategy Lab"),
            ("/simulation-lab", "Simulation Lab"),
            ("/agent-memory", "Agent Memory Center"),
            ("/risk-timeline", "Risk Event Timeline"),
            ("/setup", "Setup Wizard"),
        ]:
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(marker, response.get_data(as_text=True))

    def test_navigation_links_are_not_stranded(self):
        from agents.master_trader import miro_dashboard_server as server

        client = server.app.test_client()
        required = ["Autonomy Suite", "Risk Cockpit", "Trade Journal", "Operations", "Scoreboard", "Strategy Lab", "Simulation Lab", "Agent Memory", "Risk Timeline", "Setup Wizard", "Pipeline", "Rules"]
        for path in ["/", "/autonomy-suite", "/risk-cockpit", "/trade-journal", "/operations", "/scoreboard", "/strategy-lab", "/simulation-lab", "/agent-memory", "/risk-timeline", "/setup", "/pipeline", "/rules", "/legacy"]:
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
            ("/api/ops/events", "database"),
            ("/api/ops/metrics/history", "items"),
            ("/api/trade-journal", "items"),
            ("/api/promotion/funnel", "stages"),
            ("/api/risk-cockpit", "live_safety"),
            ("/api/mt5/reconcile", "checks"),
            ("/api/agent-memory", "handoff_docs"),
            ("/api/recovery/status", "recommended_actions"),
            ("/api/simulation-lab", "modes"),
            ("/api/setup-wizard", "steps"),
            ("/api/kill-switch", "active"),
        ]:
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(key, response.get_json())

    def test_kill_switch_controls_render(self):
        from agents.master_trader import miro_dashboard_server as server

        client = server.app.test_client()
        self.assertIn("KILL SWITCH", client.get("/setup").get_data(as_text=True))
        self.assertIn("Kill Switch", client.get("/operations").get_data(as_text=True))
        response = client.get("/api/kill-switch")
        self.assertEqual(response.status_code, 200)
        self.assertIn("active", response.get_json())

    def test_setup_wizard_fix_scan(self):
        from agents.master_trader import miro_dashboard_server as server

        client = server.app.test_client()
        response = client.post("/api/setup-wizard/fix", json={"action": "scan"})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("wizard", payload)
        self.assertIn("issues", payload["wizard"])
        self.assertIn("completion_pct", payload["wizard"])
        self.assertIn("auto_fixable", payload["wizard"])

    def test_scoreboard_records_metric_history(self):
        from agents.master_trader import miro_dashboard_server as server

        client = server.app.test_client()
        self.assertEqual(client.get("/api/scoreboard").status_code, 200)
        response = client.get("/api/ops/metrics/history?metric=balance&limit=5")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("items", payload)
        self.assertGreaterEqual(len(payload["items"]), 1)


if __name__ == "__main__":
    unittest.main()
