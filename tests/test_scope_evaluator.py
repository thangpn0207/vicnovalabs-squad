#!/usr/bin/env python3
"""
Unit tests for Tier A Scope & Risk Evaluator (squad_engine/scope_evaluator.py),
Log Compaction (squad_engine/test_harness.py), and Targeted Test resolution.
"""

import unittest
import os
from pathlib import Path
from squad_engine.scope_evaluator import (
    evaluate_scope_risk,
    ScopeRiskAssessment,
    SENSITIVE_PATH_PATTERNS,
    SAFE_FAST_PATH_PATTERNS
)
from squad_engine.test_harness import compact_execution_log
from squad_engine.stack_detector import STACK_PROFILES


class TestScopeEvaluator(unittest.TestCase):

    def test_sensitive_path_triggers_high_risk_and_soft_suggestion(self):
        sensitive_cases = [
            ["app/auth/login.py"],
            ["src/security/crypto.ts"],
            ["backend/middleware/auth_check.go"],
            [".env.production"],
            ["db/migrations/001_initial.sql"],
            ["services/payment/charge.py"],
            ["api/rbac/roles.py"]
        ]
        for files in sensitive_cases:
            res = evaluate_scope_risk(touched_files=files)
            self.assertEqual(res.risk_level, "HIGH", f"Failed for {files}")
            self.assertTrue(res.requires_adversarial_review)
            self.assertFalse(res.is_fast_path)
            self.assertIsNotNone(res.soft_suggestion)
            self.assertIn("💡", res.soft_suggestion)

    def test_safe_fast_paths_trigger_minimal_risk(self):
        safe_cases = [
            ["assets/styles/main.css", "components/button.scss"],
            ["docs/README.md", "docs/architecture.md"],
            ["public/locales/en.json", "public/locales/vi.json"],
            [".gitignore", "config.yaml"]
        ]
        for files in safe_cases:
            res = evaluate_scope_risk(touched_files=files)
            self.assertEqual(res.risk_level, "MINIMAL", f"Failed for {files}")
            self.assertTrue(res.is_fast_path)
            self.assertFalse(res.requires_adversarial_review)
            self.assertIsNone(res.soft_suggestion)

    def test_read_only_explanation_query_is_fast_path(self):
        queries = [
            "giải thích hàm calculate_tax",
            "tại sao biến này bị null",
            "nghĩa là gì khi gặp lỗi ERR_CONNECTION_REFUSED",
            "explain how the scope evaluator works",
            "what is the difference between fast-path and subagent"
        ]
        for q in queries:
            res = evaluate_scope_risk(touched_files=[], prompt=q)
            self.assertEqual(res.risk_level, "MINIMAL")
            self.assertTrue(res.is_fast_path)

    def test_sensitive_prompt_provides_soft_suggestion_without_blocking(self):
        prompt = "thêm đăng nhập bằng google oauth"
        res = evaluate_scope_risk(touched_files=[], prompt=prompt)
        self.assertIsNotNone(res.soft_suggestion)
        self.assertIn("💡", res.soft_suggestion)
        self.assertFalse(res.requires_adversarial_review)  # Soft suggestion does not force subagent


class TestLogCompactorAndTargetedTest(unittest.TestCase):

    def test_compact_execution_log_generates_receipt_and_file(self):
        stdout = "test_1 PASSED\ntest_2 PASSED\n" + ("running step...\n" * 50) + "Ran 52 tests in 2.5s\nOK\n"
        stderr = ""
        res = compact_execution_log(stdout, stderr, exit_code=0, command="pytest")
        self.assertTrue(res["is_success"])
        self.assertEqual(res["exit_code"], 0)
        self.assertTrue(os.path.exists(res["log_path"]))
        self.assertIn("✅ [EXECUTION RECEIPT]", res["compact_summary"])
        self.assertIn("Ran 52 tests in 2.5s", res["compact_summary"])
        self.assertLessEqual(len(res["compact_summary"].splitlines()), 5)

        # Cleanup log
        try:
            os.remove(res["log_path"])
        except Exception:
            pass

    def test_python_targeted_test_command_maps_file_to_test(self):
        py_stack = STACK_PROFILES["python"]
        # When modifying squad_engine/gate.py, should map to tests/test_gate.py if test exists
        cmd = py_stack.get_targeted_test_command(
            modified_files=["squad_engine/gate.py"],
            workspace_dir=str(Path(__file__).parent.parent)
        )
        self.assertIn("tests/test_gate.py", cmd)

    def test_fallback_test_runner_when_no_targeted_match(self):
        py_stack = STACK_PROFILES["python"]
        cmd = py_stack.get_targeted_test_command(modified_files=[])
        self.assertEqual(cmd, "pytest")


if __name__ == "__main__":
    unittest.main()
