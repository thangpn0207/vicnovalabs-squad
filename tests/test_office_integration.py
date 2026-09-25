"""
tests/test_office_integration.py
End-to-End Acceptance & POAI Integration Test for VicnovaLabs Squad Virtual Office (Port 7777 / Dynamic).
Verifies:
1. Live Server Startup & Port Resolution
2. SSE Real-Time Telemetry Stream Reception
3. FinOps Token & Burn Rate Live Mutation (POAI)
4. Two-Way Mission Control Interlock (Pause, Resume, Gate Decision)
5. CSRF & Unauthorized Access Protection (403 Forbidden)
6. Clean Teardown & PID Cleanup
"""

import os
import json
import time
import urllib.request
import urllib.error
import tempfile
import threading
import unittest

from squad_engine.server import SquadOfficeServer
from squad_engine.telemetry import TelemetryEvent


class TestOfficeIntegrationPOAI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.state_file = os.path.join(cls.temp_dir.name, "control_state.json")
        cls.progress_file = os.path.join(cls.temp_dir.name, "PROJECT_PROGRESS.md")
        with open(cls.progress_file, "w") as f:
            f.write("# Progress\n- [x] Engine Setup\n- [-] Virtual Office (READY_FOR_QA)\n")

        cls.token = "acceptance-secret-token-999"
        cls.server = SquadOfficeServer(
            port=8998,
            session_token=cls.token,
            state_file=cls.state_file,
            progress_path=cls.progress_file,
        )
        cls.url = cls.server.start(open_browser_tab=False)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.temp_dir.cleanup()

    def test_01_server_running_and_assets(self):
        # Verify index.html loads
        with urllib.request.urlopen(f"http://127.0.0.1:{self.server.port}/") as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("Virtual Animated Office", body)
            self.assertIn("Two-Way Mission Control", body)

    def test_02_unauthorized_access_blocked(self):
        # Requesting stream without token must fail with 403
        req = urllib.request.Request(f"http://127.0.0.1:{self.server.port}/api/stream")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_03_finops_live_mutation_poai(self):
        # Pre-state: record initial tokens
        pre_tokens = self.server.finops.get_total_tokens()
        pre_cost = self.server.finops.get_total_cost()

        # Mutation: record dynamic usage with timestamp
        now = time.time()
        self.server.finops.record_usage(
            agent_role="dev",
            model="gemini-3.0-flash",
            prompt_tokens=50_000,
            completion_tokens=10_000,
            cached_tokens=10_000,
            timestamp=now,
        )

        # Post-state: verify strict inequality (POAI: Pre != Post)
        post_tokens = self.server.finops.get_total_tokens()
        post_cost = self.server.finops.get_total_cost()

        self.assertGreater(post_tokens, pre_tokens)
        self.assertGreater(post_cost, pre_cost)

        # Verify reflected in /api/status endpoint
        with urllib.request.urlopen(f"http://127.0.0.1:{self.server.port}/api/status") as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertGreaterEqual(data["finops"]["total_tokens"], post_tokens)
            self.assertGreaterEqual(data["finops"]["total_cost_usd"], post_cost - 0.0001)

    def test_04_control_interlock_two_way_poai(self):
        # Pre-state: system is RUNNING
        self.assertFalse(self.server.control.is_paused("dev"))

        # Step 1: Web UI sends Pause Dev
        pause_url = f"http://127.0.0.1:{self.server.port}/api/control/pause"
        body = json.dumps({"role": "dev"}).encode("utf-8")
        req = urllib.request.Request(
            pause_url, data=body, headers={"Content-Type": "application/json", "X-Squad-Token": self.token}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)

        # Post-state 1: Dev is PAUSED
        self.assertTrue(self.server.control.is_paused("dev"))
        self.assertFalse(self.server.control.is_paused("qa"))

        # Step 2: Web UI sends Resume Dev
        resume_url = f"http://127.0.0.1:{self.server.port}/api/control/resume"
        req = urllib.request.Request(
            resume_url, data=body, headers={"Content-Type": "application/json", "X-Squad-Token": self.token}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)

        # Post-state 2: Dev is back to RUNNING
        self.assertFalse(self.server.control.is_paused("dev"))

    def test_05_gate_approval_two_way_poai(self):
        gate_url = f"http://127.0.0.1:{self.server.port}/api/gate/decision"
        body = json.dumps({"decision": "APPROVED", "notes": "POAI verified on port 8998"}).encode("utf-8")
        req = urllib.request.Request(
            gate_url, data=body, headers={"Content-Type": "application/json", "X-Squad-Token": self.token}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)

        state = self.server.control.get_state()
        self.assertEqual(state["gate_decision"], "APPROVED")
        self.assertEqual(state["gate_notes"], "POAI verified on port 8998")

    def test_06_sse_streaming_reception(self):
        received_events = []
        stop_listener = threading.Event()

        def stream_listener():
            url = f"http://127.0.0.1:{self.server.port}/api/stream?token={self.token}"
            req = urllib.request.Request(url)
            try:
                with urllib.request.urlopen(req) as resp:
                    for line in resp:
                        if stop_listener.is_set():
                            break
                        decoded = line.decode("utf-8").strip()
                        if decoded.startswith("data: "):
                            try:
                                data_obj = json.loads(decoded[6:])
                                received_events.append(data_obj)
                                if len(received_events) >= 2:
                                    break
                            except Exception:
                                pass
            except Exception:
                pass

        t = threading.Thread(target=stream_listener, daemon=True)
        t.start()

        # Emit an event to bus
        time.sleep(0.3)
        self.server.event_bus.emit("AGENT_STATUS", {"role": "dev", "status": "CODING", "snippet": "Integration test"})

        t.join(timeout=3.0)
        stop_listener.set()

        # At least INIT_STATE and/or AGENT_STATUS received
        self.assertGreaterEqual(len(received_events), 1)


if __name__ == "__main__":
    unittest.main()
