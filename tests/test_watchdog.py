#!/usr/bin/env python3
"""
Unit tests for Subagent Watchdog & Circuit Breaker.
"""

import unittest
from squad_engine.watchdog import audit_subagents_health


class TestSubagentWatchdog(unittest.TestCase):
    def test_healthy_subagents(self):
        subagents = [
            {"conversationId": "sub-1", "role": "dev-agent", "state": "running", "stateDetail": "Working on task"},
            {"conversationId": "sub-2", "role": "qa-agent", "state": "idle", "stateDetail": "Waiting for input"}
        ]
        res = audit_subagents_health(subagents)
        self.assertEqual(res["status"], "HEALTHY")
        self.assertFalse(res["stop_required"])
        self.assertFalse(res["is_quota_exhausted"])
        self.assertEqual(len(res["kill_conversation_ids"]), 0)

    def test_quota_exhausted_429(self):
        subagents = [
            {
                "conversationId": "sub-quota-1",
                "role": "dev-agent",
                "state": "errored",
                "stateDetail": "GoogleGenerativeAIError: 429 Resource has been exhausted (e.g. check quota)."
            }
        ]
        res = audit_subagents_health(subagents)
        self.assertEqual(res["status"], "ACTION_REQUIRED")
        self.assertTrue(res["stop_required"])
        self.assertTrue(res["is_quota_exhausted"])
        self.assertIn("sub-quota-1", res["kill_conversation_ids"])
        self.assertIn("429", res["alert_message"])

    def test_crashed_subagent(self):
        subagents = [
            {
                "conversationId": "sub-crash-1",
                "role": "debug-agent",
                "state": "errored",
                "stateDetail": "Process crashed with unhandled exception"
            }
        ]
        res = audit_subagents_health(subagents)
        self.assertEqual(res["status"], "ACTION_REQUIRED")
        self.assertTrue(res["stop_required"])
        self.assertFalse(res["is_quota_exhausted"])
        self.assertIn("sub-crash-1", res["kill_conversation_ids"])

    def test_waiting_for_dependents_hang(self):
        subagents = [
            {
                "conversationId": "sub-dep-1",
                "role": "squad-dev-ui",
                "state": "waiting_for_dependents",
                "stateDetail": "Waiting for unreleased child background task (task-96)"
            }
        ]
        res = audit_subagents_health(subagents)
        self.assertEqual(res["status"], "ACTION_REQUIRED")
        self.assertTrue(res["stop_required"])
        self.assertIn("sub-dep-1", res["kill_conversation_ids"])
        self.assertIn("ORPHANED_DEPENDENTS_HANG", res["alert_message"])

    def test_reap_zombie_subagents(self):
        from squad_engine.watchdog import reap_zombie_subagents
        subagents = [
            {"conversationId": "sub-ok", "role": "dev-agent", "state": "idle"},
            {"conversationId": "sub-bad-1", "role": "squad-dev-ui", "state": "waiting_for_dependents"},
            {"conversationId": "sub-bad-2", "role": "qa-agent", "state": "canceling"}
        ]
        kill_list = reap_zombie_subagents(subagents)
        self.assertEqual(sorted(kill_list), ["sub-bad-1", "sub-bad-2"])


if __name__ == "__main__":
    unittest.main()

