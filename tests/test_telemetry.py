"""
tests/test_telemetry.py
Unit tests for squad_engine/telemetry.py (Event Bus, Transcript Tailer, Progress Watcher)
"""

import os
import json
import time
import tempfile
import unittest
from squad_engine.telemetry import TelemetryEvent, TelemetryEventBus, TranscriptTailer, ProgressWatcher


class TestTelemetry(unittest.TestCase):
    def setUp(self):
        self.bus = TelemetryEventBus(max_history=5)

    def test_event_bus_publish_and_subscribe(self):
        q = self.bus.subscribe()
        event = self.bus.emit("AGENT_STATUS", {"role": "dev", "status": "CODING"})

        self.assertEqual(event.event_type, "AGENT_STATUS")
        received = q.get(timeout=1.0)
        self.assertEqual(received.id, event.id)
        self.assertEqual(received.data["role"], "dev")

        # History ring buffer
        for i in range(10):
            self.bus.emit("STEP", {"index": i})

        history = self.bus.get_history(limit=5)
        self.assertEqual(len(history), 5)
        self.assertEqual(history[-1]["data"]["index"], 9)

        self.bus.unsubscribe(q)

    def test_sse_payload_formatting(self):
        event = TelemetryEvent(event_type="TOKEN_USAGE", data={"tokens": 150})
        payload = event.to_sse_payload()
        self.assertTrue(payload.startswith("id: "))
        self.assertIn("event: TOKEN_USAGE\n", payload)
        self.assertIn('"tokens": 150', payload)
        self.assertTrue(payload.endswith("\n\n"))

    def test_progress_watcher(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".md") as f:
            f.write("# Progress\n- [x] Task 1\n- [x] Task 2\n- [-] Task 3 (READY_FOR_QA)\n")
            f_path = f.name

        try:
            watcher = ProgressWatcher(self.bus, progress_path=f_path)
            data = watcher.parse_progress()
            self.assertEqual(data["completed_tasks"], 2)
            self.assertEqual(data["total_tasks"], 3)
            self.assertEqual(data["completion_percentage"], 67)

            emitted = watcher.check_and_emit()
            self.assertIsNotNone(emitted)
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_transcript_tailer_parsing(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".jsonl") as f:
            f_path = f.name

        try:
            q = self.bus.subscribe()
            tailer = TranscriptTailer(self.bus, transcript_path=f_path, poll_interval=0.1)

            # Write a step
            step_obj = {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "thinking": "Writing code for virtual office",
                "tool_calls": [
                    {
                        "call": {
                            "name": "write_to_file",
                            "arguments": {"TargetFile": "/app/test.py", "toolSummary": "Write code"},
                        }
                    }
                ],
            }
            with open(f_path, "a") as f:
                f.write(json.dumps(step_obj) + "\n")

            tailer._tail_file(f_path)

            events = []
            while not q.empty():
                events.append(q.get_nowait())

            event_types = [e.event_type for e in events]
            self.assertIn("TOOL_CALL", event_types)
            self.assertIn("AGENT_STATUS", event_types)
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_transcript_tailer_with_finops(self):
        from squad_engine.finops import FinOpsEngine
        finops = FinOpsEngine()
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".jsonl") as f:
            f_path = f.name

        try:
            q = self.bus.subscribe()
            tailer = TranscriptTailer(self.bus, transcript_path=f_path, finops=finops, poll_interval=0.1)

            step_obj = {
                "step_index": 2,
                "type": "PLANNER_RESPONSE",
                "thinking": "Dev agent coding virtual office canvas",
                "tool_calls": [
                    {
                        "call": {
                            "name": "write_to_file",
                            "arguments": {"TargetFile": "/app/web.js", "toolSummary": "Write canvas code"},
                        }
                    }
                ],
            }
            with open(f_path, "a") as f:
                f.write(json.dumps(step_obj) + "\n")

            tailer._tail_file(f_path)

            # Verify finops recorded tokens
            self.assertGreater(finops.get_total_tokens(), 0)
            self.assertGreater(finops.get_total_cost(), 0.0)

            # Verify TOKEN_USAGE event emitted
            events = []
            while not q.empty():
                events.append(q.get_nowait())
            types = [e.event_type for e in events]
            self.assertIn("TOKEN_USAGE", types)
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)


if __name__ == "__main__":
    unittest.main()
