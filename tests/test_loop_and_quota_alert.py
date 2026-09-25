"""
tests/test_loop_and_quota_alert.py
Unit tests for Loop Detection, Quota Exhaustion Alerts, Multi-file Tailing, and Accurate Token Telemetry.
"""

import os
import json
import tempfile
import unittest
from squad_engine.telemetry import (
    TelemetryEventBus,
    TranscriptTailer,
    extract_tool_call_info,
    TranscriptFileState,
)
from squad_engine.finops import FinOpsEngine


class TestLoopAndQuotaAlert(unittest.TestCase):
    def setUp(self):
        self.bus = TelemetryEventBus()
        self.finops = FinOpsEngine(alert_threshold_usd=0.01, hard_limit_usd=0.02)
        self.queue = self.bus.subscribe()

    def tearDown(self):
        self.bus.unsubscribe(self.queue)

    def _drain_events(self):
        events = []
        while not self.queue.empty():
            events.append(self.queue.get_nowait())
        return events

    def test_extract_tool_call_info_antigravity_format(self):
        # Native Antigravity format
        tc = {
            "name": "run_command",
            "args": {
                "CommandLine": "python3 -m unittest",
                "toolSummary": "Run test suite",
                "toolAction": "Running tests",
            },
        }
        info = extract_tool_call_info(tc)
        self.assertEqual(info["name"], "run_command")
        self.assertEqual(info["summary"], "Run test suite")
        self.assertEqual(info["action"], "Running tests")
        self.assertEqual(info["args"]["CommandLine"], "python3 -m unittest")

    def test_extract_tool_call_info_nested_format(self):
        # OpenAI / nested format
        tc = {
            "call": {
                "name": "write_to_file",
                "arguments": {
                    "TargetFile": "/app/src/index.ts",
                    "toolSummary": "Create file",
                },
            }
        }
        info = extract_tool_call_info(tc)
        self.assertEqual(info["name"], "write_to_file")
        self.assertEqual(info["summary"], "Create file")

    def test_identical_command_loop_detection(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".jsonl") as f:
            f_path = f.name

        try:
            tailer = TranscriptTailer(self.bus, transcript_path=f_path, finops=self.finops)

            # Write 3 identical commands
            for i in range(1, 4):
                entry = {
                    "step_index": i,
                    "type": "PLANNER_RESPONSE",
                    "thinking": "Retrying failing test command",
                    "tool_calls": [
                        {
                            "name": "run_command",
                            "args": {"CommandLine": "flutter test test/app_test.dart"},
                        }
                    ],
                }
                with open(f_path, "a") as f:
                    f.write(json.dumps(entry) + "\n")
                tailer._tail_file(f_path)

            events = self._drain_events()
            loop_events = [e for e in events if e.event_type == "LOOP_DETECTED"]
            self.assertGreaterEqual(len(loop_events), 1)
            self.assertEqual(loop_events[0].data["error_type"], "IDENTICAL_COMMAND_LOOP")
            self.assertEqual(loop_events[0].data["count"], 3)
            self.assertIn("flutter test", loop_events[0].data["command"])
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_screenshot_loop_detection(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".jsonl") as f:
            f_path = f.name

        try:
            tailer = TranscriptTailer(self.bus, transcript_path=f_path, finops=self.finops)

            # Write 4 screencap calls
            for i in range(1, 5):
                entry = {
                    "step_index": i,
                    "type": "PLANNER_RESPONSE",
                    "thinking": "Taking screenshot",
                    "tool_calls": [
                        {
                            "name": "run_command",
                            "args": {"CommandLine": f"adb exec-out screencap -p > /tmp/screen_{i}.png"},
                        }
                    ],
                }
                with open(f_path, "a") as f:
                    f.write(json.dumps(entry) + "\n")
                tailer._tail_file(f_path)

            events = self._drain_events()
            loop_events = [e for e in events if e.event_type == "LOOP_DETECTED"]
            self.assertGreaterEqual(len(loop_events), 1)
            self.assertEqual(loop_events[-1].data["error_type"], "SCREENSHOT_LOOP_VIOLATION")
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_quota_exhausted_429_detection(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".jsonl") as f:
            f_path = f.name

        try:
            tailer = TranscriptTailer(self.bus, transcript_path=f_path, finops=self.finops)

            entry = {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "thinking": "Error: 429 RESOURCE_EXHAUSTED Quota exceeded for model",
                "content": "API returned 429 RESOURCE_EXHAUSTED: Rate limit reached.",
                "tool_calls": [],
            }
            with open(f_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
            tailer._tail_file(f_path)

            events = self._drain_events()
            quota_events = [e for e in events if e.event_type == "QUOTA_EXHAUSTED"]
            self.assertGreaterEqual(len(quota_events), 1)
            self.assertEqual(quota_events[0].data["error_type"], "RESOURCE_EXHAUSTED_429")
            self.assertIn("rate limit", quota_events[0].data["message"].lower())
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_budget_hard_limit_detection(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".jsonl") as f:
            f_path = f.name

        try:
            # Set tiny budget cap to trigger limit
            finops = FinOpsEngine(alert_threshold_usd=0.0001, hard_limit_usd=0.0002)
            tailer = TranscriptTailer(self.bus, transcript_path=f_path, finops=finops)

            # A step with 50,000 characters context -> cost will exceed hard limit
            entry = {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "thinking": "Generating heavy codebase " * 1000,
                "content": "Heavy code payload " * 1000,
                "tool_calls": [{"name": "write_to_file", "args": {"TargetFile": "/tmp/heavy.py"}}],
            }
            with open(f_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
            tailer._tail_file(f_path)

            events = self._drain_events()
            quota_events = [e for e in events if e.event_type == "QUOTA_EXHAUSTED"]
            self.assertGreaterEqual(len(quota_events), 1)
            self.assertEqual(quota_events[0].data["error_type"], "BUDGET_HARD_LIMIT")
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_subagent_role_identification_and_tokens(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".jsonl") as f:
            f_path = f.name

        try:
            tailer = TranscriptTailer(self.bus, transcript_path=f_path, finops=self.finops)

            # Subagent step 0 declaring identity
            step0 = {
                "step_index": 0,
                "type": "USER_INPUT",
                "content": "# Task: You are squad-dev (Staff Full-Stack Software Engineer)",
            }
            step1 = {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "thinking": "Implementing the requested API endpoint",
                "tool_calls": [
                    {
                        "name": "write_to_file",
                        "args": {"TargetFile": "squad_engine/api.py", "toolSummary": "Write API code"},
                    }
                ],
            }

            with open(f_path, "a") as f:
                f.write(json.dumps(step0) + "\n")
                f.write(json.dumps(step1) + "\n")
            tailer._tail_file(f_path)

            events = self._drain_events()
            token_events = [e for e in events if e.event_type == "TOKEN_USAGE"]
            self.assertGreaterEqual(len(token_events), 1)
            self.assertEqual(token_events[0].data["role"], "dev")

            tool_events = [e for e in events if e.event_type == "TOOL_CALL"]
            self.assertGreaterEqual(len(tool_events), 1)
            self.assertEqual(tool_events[0].data["role"], "dev")
            self.assertEqual(tool_events[0].data["tool_name"], "write_to_file")
            self.assertEqual(tool_events[0].data["tool_summary"], "Write API code")
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)


if __name__ == "__main__":
    unittest.main()
