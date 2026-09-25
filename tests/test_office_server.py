"""
tests/test_office_server.py
Unit tests for squad_engine/server.py and squad_engine/control.py (HTTP endpoints, auth, SSE, RPCs)
"""

import os
import json
import time
import urllib.request
import urllib.error
import tempfile
import unittest

from squad_engine.server import SquadOfficeServer
from squad_engine.control import ControlBridge


class TestOfficeServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.state_file = os.path.join(cls.temp_dir.name, "control_state.json")
        cls.token = "test-secret-token-12345"
        cls.server = SquadOfficeServer(
            port=8990,
            session_token=cls.token,
            state_file=cls.state_file,
            progress_path=os.path.join(cls.temp_dir.name, "PROGRESS.md"),
        )
        cls.url = cls.server.start(open_browser_tab=False)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.temp_dir.cleanup()

    def test_unauthorized_request_rejected(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.server.port}/api/stream")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_status_endpoint(self):
        url = f"http://127.0.0.1:{self.server.port}/api/status"
        with urllib.request.urlopen(url) as response:
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode("utf-8"))
            self.assertEqual(data["status"], "online")
            self.assertIn("finops", data)
            self.assertIn("control", data)
            self.assertIn("progress", data)

    def test_control_pause_and_resume_rpc(self):
        # Pause Dev
        pause_url = f"http://127.0.0.1:{self.server.port}/api/control/pause"
        body = json.dumps({"role": "dev"}).encode("utf-8")
        req = urllib.request.Request(
            pause_url, data=body, headers={"Content-Type": "application/json", "X-Squad-Token": self.token}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertIn("dev", data["state"]["paused_agents"])

        # Check bridge directly
        self.assertTrue(self.server.control.is_paused("dev"))
        self.assertFalse(self.server.control.is_paused("qa"))

        # Resume Dev
        resume_url = f"http://127.0.0.1:{self.server.port}/api/control/resume"
        req = urllib.request.Request(
            resume_url, data=body, headers={"Content-Type": "application/json", "X-Squad-Token": self.token}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertNotIn("dev", data["state"]["paused_agents"])

    def test_gate_decision_rpc(self):
        gate_url = f"http://127.0.0.1:{self.server.port}/api/gate/decision"
        body = json.dumps({"decision": "APPROVED", "notes": "Fidelity >= 85%"}).encode("utf-8")
        req = urllib.request.Request(
            gate_url, data=body, headers={"Content-Type": "application/json", "X-Squad-Token": self.token}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertEqual(data["state"]["gate_decision"], "APPROVED")

    def test_ingest_telemetry_event(self):
        event_url = f"http://127.0.0.1:{self.server.port}/api/telemetry/event"
        body = json.dumps({"event_type": "TEST_EVENT", "data": {"foo": "bar"}}).encode("utf-8")
        req = urllib.request.Request(
            event_url, data=body, headers={"Content-Type": "application/json", "X-Squad-Token": self.token}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertIn("event_id", data)


if __name__ == "__main__":
    unittest.main()
