#!/usr/bin/env python3
"""
Tests for target_agent naming consistency across all gate paths.
Verifies that all dispatch paths return squad-{role} format for TypeName
consistency with define_subagent naming convention.
"""

import unittest
from unittest.mock import patch

from squad_engine.gate import squad_gate


class TestGateNamingConsistency(unittest.TestCase):
    """All gate paths must return target_agent in 'squad-{role}' format."""

    def _assert_squad_naming(self, result, expected_role=None):
        """Helper: verify target_agent uses squad-{role} format."""
        target = result.get("target_agent", "")
        if target:
            self.assertTrue(
                target.startswith("squad-"),
                f"target_agent '{target}' does not use squad-{{role}} format. "
                f"Expected 'squad-{expected_role or '...'}'"
            )

    def test_single_task_returns_squad_naming(self):
        """Single task exemption should return squad-{role}."""
        result = squad_gate("chỉ giải thích lý do tại sao")
        self._assert_squad_naming(result)
        self.assertEqual(result["execution_mode"], "inline")

    @patch("squad_engine.gate.audit_adb_devices")
    def test_standard_triage_returns_squad_naming(self, mock_devices):
        """Standard triage dispatch should return squad-{role}."""
        mock_devices.return_value = {
            "total_count": 0, "physical_devices": [], "emulators": [],
            "has_physical_device": False, "mode": "none", "can_run_dual_device": False
        }
        result = squad_gate("build the authentication module", mode="suggest")
        self._assert_squad_naming(result, "dev")

    @patch("squad_engine.gate.audit_adb_devices")
    def test_qa_dispatch_returns_squad_naming(self, mock_devices):
        """QA dispatch should return squad-qa, not qa-agent."""
        mock_devices.return_value = {
            "total_count": 0, "physical_devices": [], "emulators": [],
            "has_physical_device": False, "mode": "none", "can_run_dual_device": False
        }
        result = squad_gate(
            "HandoffManifest: self_test_result PASSED, verification_command: flutter test",
            mode="auto"
        )
        if result.get("target_agent"):
            self._assert_squad_naming(result, "qa")

    @patch("squad_engine.gate.audit_adb_devices")
    def test_auto_mode_returns_squad_naming(self, mock_devices):
        """Auto mode dispatch should return squad-{role}."""
        mock_devices.return_value = {
            "total_count": 0, "physical_devices": [], "emulators": [],
            "has_physical_device": False, "mode": "none", "can_run_dual_device": False
        }
        result = squad_gate("build a new feature for user dashboard", mode="auto")
        self._assert_squad_naming(result)

    @patch("squad_engine.gate.audit_adb_devices")
    def test_explicit_squad_returns_squad_naming(self, mock_devices):
        """Explicit squad summon should return squad-{role}."""
        mock_devices.return_value = {
            "total_count": 0, "physical_devices": [], "emulators": [],
            "has_physical_device": False, "mode": "none", "can_run_dual_device": False
        }
        result = squad_gate("gọi squad dev-agent để build feature login", mode="suggest")
        self._assert_squad_naming(result)

    @patch("squad_engine.gate.audit_adb_devices")
    def test_option_selection_returns_squad_naming(self, mock_devices):
        """Option selection dispatch should return squad-{role}."""
        mock_devices.return_value = {
            "total_count": 0, "physical_devices": [], "emulators": [],
            "has_physical_device": False, "mode": "none", "can_run_dual_device": False
        }
        result = squad_gate("thực hiện phương án 1", mode="auto", active_domain="dev")
        self._assert_squad_naming(result)

    def test_all_gate_results_never_use_role_agent_format(self):
        """Exhaustive check: no gate path should return '{role}-agent' as target_agent."""
        test_prompts = [
            "chỉ sửa typo",
            "giải thích code này",
            "build authentication module",
            "thực hiện option A",
        ]
        for prompt in test_prompts:
            result = squad_gate(prompt, mode="suggest")
            target = result.get("target_agent", "")
            if target:
                self.assertFalse(
                    target.endswith("-agent"),
                    f"Prompt '{prompt}' returned legacy naming '{target}'"
                )


class TestTaskPlanNaming(unittest.TestCase):
    """task_plan.py decompose_large_task should use squad-{role} naming."""

    @patch("squad_engine.task_plan.audit_adb_devices")
    def test_decompose_uses_squad_naming(self, mock_devices):
        mock_devices.return_value = {
            "total_count": 0, "physical_devices": [], "emulators": [],
            "has_physical_device": False, "mode": "none", "can_run_dual_device": False
        }
        from squad_engine.task_plan import decompose_large_task
        result = decompose_large_task("build toàn bộ authentication + chat + settings")

        for st in result["subtasks"]:
            target = st.get("target_agent", "")
            self.assertTrue(
                target.startswith("squad-"),
                f"Subtask '{st['title']}' has legacy naming '{target}'"
            )


if __name__ == "__main__":
    unittest.main()
