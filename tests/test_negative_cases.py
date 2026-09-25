#!/usr/bin/env python3
"""
Phase 7.2 — Comprehensive Negative Testing Suite for VicnovaLabs Squad EDQA.

Verifies system resilience against:
1. QA report PASS without execution record
2. PASS with missing or empty evidence directory
3. PASS with stale evidence files
4. Test runner exit code != 0
5. Pre and post screenshots with identical content (zero mutation)
6. Log files containing unhandled exceptions or crash signatures
7. ADB device in offline state
8. ADB device in unauthorized state
9. App package not installed on target device
10. Insufficient device storage (<500MB)
11. Handoff manifest missing requirement IDs in strict traceability mode
12. Acceptance signoff missing requirement IDs in strict traceability mode
13. Acceptance journey with zero interactive commands (passive visual only)
14. Multi-device blindspot (untested target platforms)
15. Worktree merge rejected when main working tree is dirty
16. Worktree merge rejected when test-before-merge fails
17. Memory filtering excludes superseded decisions from active context
"""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from squad_engine.handoffs import validate_handoff_payload
from squad_engine.evidence_oracle import validate_evidence_bundle, validate_runner_result
from squad_engine.devices import run_adb_preflight
from squad_engine.worktrees import merge_task_worktree
from squad_engine.memory import SquadMemory


class TestNegativeQAReports(unittest.TestCase):
    """Negative tests for QA signoff, oracle, and anti-false-PASS guards."""

    def setUp(self):
        self.base_acceptance_payload = {
            "module": "AuthModule",
            "target_platforms": ["android:emulator-5554"],
            "fresh_test_identifier": "nonce_test_9999",
            "interactive_journey": [
                {"device": "emulator-5554", "action": "agent-device tap #login_button", "observed_delta": "navigated_home"}
            ],
            "state_mutation_delta": {"pre": "logged_out", "post": "logged_in"},
            "live_evidence": "Logcat trace: User authenticated successfully at 19:40:00",
            "anti_deception_checks": {
                "no_passive_visual_only": True,
                "all_target_devices_interacted": True,
                "stale_data_ruled_out": True,
                "silent_errors_ruled_out": True
            },
            "verdict": "PASS"
        }

    def test_pass_without_execution_record_rejected_in_strict_mode(self):
        """Negative Test 1: QA report PASS without runner_exit_code must be rejected."""
        payload = dict(self.base_acceptance_payload)
        # runner_exit_code omitted
        res = validate_handoff_payload("acceptance", payload, strict_evidence=True)
        self.assertFalse(res["valid"])
        self.assertTrue(any("runner_exit_code" in e for e in res["errors"]))

    def test_pass_with_missing_evidence_dir_rejected_in_strict_mode(self):
        """Negative Test 2: QA report PASS without evidence_dir must be rejected."""
        payload = dict(self.base_acceptance_payload)
        payload["runner_exit_code"] = 0
        # evidence_dir omitted
        res = validate_handoff_payload("acceptance", payload, strict_evidence=True)
        self.assertFalse(res["valid"])
        self.assertTrue(any("evidence_dir" in e for e in res["errors"]))

    def test_pass_with_nonexistent_evidence_dir_rejected(self):
        """Negative Test 2b: QA report PASS with non-existent evidence directory must be rejected."""
        payload = dict(self.base_acceptance_payload)
        payload["runner_exit_code"] = 0
        payload["evidence_dir"] = "/nonexistent/squad_evidence_bundle_path_xyz"
        res = validate_handoff_payload("acceptance", payload, strict_evidence=True)
        self.assertFalse(res["valid"])
        self.assertTrue(any("Oracle Violation" in e for e in res["errors"]))

    def test_pass_with_failed_runner_exit_code_rejected(self):
        """Negative Test 4: runner_exit_code != 0 must be hard-rejected by oracle."""
        payload = dict(self.base_acceptance_payload)
        payload["runner_exit_code"] = 1
        res = validate_handoff_payload("acceptance", payload)
        self.assertFalse(res["valid"])
        self.assertTrue(any("Oracle Violation: Test runner exited with code 1" in e for e in res["errors"]))

    def test_pass_with_stale_evidence_rejected_in_strict_mode(self):
        """Negative Test 3: Evidence files older than max_age_seconds must fail under strict staleness."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "step_01_pre.png"
            p.write_bytes(b"A" * 15000)
            # Set mtime to 600s ago
            old_time = time.time() - 600
            os.utime(p, (old_time, old_time))

            res = validate_evidence_bundle(td, max_age_seconds=300, strict_staleness=True)
            self.assertFalse(res["valid"])
            self.assertTrue(any("EVIDENCE_STALE" in e for e in res["errors"]))

    def test_identical_screenshots_rejected(self):
        """Negative Test 5: Identical pre/post screenshots must be rejected (no mutation)."""
        with tempfile.TemporaryDirectory() as td:
            content = b"IDENTICAL_SCREENSHOT_BYTES" * 1000
            (Path(td) / "step_01_pre.png").write_bytes(content)
            (Path(td) / "step_01_post.png").write_bytes(content)

            res = validate_evidence_bundle(td)
            self.assertFalse(res["valid"])
            self.assertTrue(any("UI_ACTION_FAILED" in e for e in res["errors"]))

    def test_log_error_signatures_rejected(self):
        """Negative Test 6: Fatal crash or exception in log files must be rejected."""
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "test.log").write_text("Fatal Error: Unhandled Exception: NullPointerException at line 42")
            res = validate_evidence_bundle(td)
            self.assertFalse(res["valid"])
            self.assertTrue(any("Error signature" in e for e in res["errors"]))


class TestNegativeADBScenarios(unittest.TestCase):
    """Negative tests for ADB device preflight: offline, unauthorized, wrong package, disk space."""

    def test_adb_device_offline_rejected(self):
        """Negative Test 7: Device offline returns ready=False with descriptive error."""
        with patch("squad_engine.devices.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="offline\n", returncode=0)
            result = run_adb_preflight("emulator-5554")
        self.assertFalse(result["ready"])
        self.assertEqual(result["checks"].get("device_state"), "offline")
        self.assertTrue(any("offline" in e for e in result["errors"]))

    def test_adb_device_unauthorized_rejected(self):
        """Negative Test 8: Device unauthorized returns ready=False with fingerprint instruction."""
        with patch("squad_engine.devices.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="unauthorized\n", returncode=0)
            result = run_adb_preflight("emulator-5554")
        self.assertFalse(result["ready"])
        self.assertEqual(result["checks"].get("device_state"), "unauthorized")
        self.assertTrue(any("unauthorized" in e for e in result["errors"]))

    def test_adb_wrong_package_id_rejected(self):
        """Negative Test 9: Target app package not installed on device is rejected."""
        def mock_subprocess(cmd, *args, **kwargs):
            if "get-state" in cmd:
                return MagicMock(stdout="device\n", returncode=0)
            if "echo" in cmd:
                return MagicMock(stdout="__ok__\n", returncode=0)
            if "pm list packages" in cmd:
                return MagicMock(stdout="package:com.android.settings\npackage:com.google.android.gms\n", returncode=0)
            if "df" in cmd:
                return MagicMock(stdout="/data: 2000000 1000000 1000000 50% /data\n", returncode=0)
            if "wm size" in cmd:
                return MagicMock(stdout="Physical size: 1080x1920\n", returncode=0)
            return MagicMock(stdout="", returncode=0)

        with patch("squad_engine.devices.subprocess.run", side_effect=mock_subprocess):
            result = run_adb_preflight("emulator-5554", package_id="com.nonexistent.app")
        self.assertFalse(result["ready"])
        self.assertFalse(result["checks"]["app_installed"])
        self.assertTrue(any("com.nonexistent.app" in e for e in result["errors"]))

    def test_adb_insufficient_storage_rejected(self):
        """Negative Test 10: Device storage < 500MB free is rejected."""
        def mock_subprocess(cmd, *args, **kwargs):
            if "get-state" in cmd:
                return MagicMock(stdout="device\n", returncode=0)
            if "echo" in cmd:
                return MagicMock(stdout="__ok__\n", returncode=0)
            if "df" in cmd:
                # 100,000 KB = ~97 MB free (below 500MB threshold)
                return MagicMock(stdout="Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-0 2000000 1900000 100000 95% /data\n", returncode=0)
            if "wm size" in cmd:
                return MagicMock(stdout="Physical size: 1080x1920\n", returncode=0)
            return MagicMock(stdout="", returncode=0)

        with patch("squad_engine.devices.subprocess.run", side_effect=mock_subprocess):
            result = run_adb_preflight("emulator-5554", min_storage_mb=500)
        self.assertFalse(result["ready"])
        self.assertFalse(result["checks"]["storage_ok"])
        self.assertTrue(any("Insufficient storage" in e for e in result["errors"]))


class TestNegativeTraceabilityAndScope(unittest.TestCase):
    """Negative tests for requirement traceability and POAI scope integrity."""

    def test_manifest_missing_requirement_ids_rejected_in_strict_mode(self):
        """Negative Test 11: Manifest without requirement_ids rejected in strict mode."""
        payload = {
            "module": "Payment",
            "modified_files": ["payment.py"],
            "self_test_result": "PASSED",
            "verification_command": "python3 -m unittest",
            "coverage_report": {
                "line_coverage_pct": 90.0,
                "branch_coverage_pct": 85.0,
                "tool": "pytest-cov",
                "meets_threshold": True
            }
        }
        res = validate_handoff_payload("manifest", payload, strict_traceability=True)
        self.assertFalse(res["valid"])
        self.assertTrue(any("requirement_ids" in e for e in res["errors"]))

    def test_acceptance_missing_requirement_ids_rejected_in_strict_mode(self):
        """Negative Test 12: Acceptance without requirement_ids rejected in strict mode."""
        payload = {
            "module": "Payment",
            "target_platforms": ["web"],
            "fresh_test_identifier": "test_id_123",
            "interactive_journey": [{"device": "chrome", "action": "click #pay"}],
            "state_mutation_delta": {"pre": "0", "post": "1"},
            "live_evidence": "console log output with at least 15 characters",
            "anti_deception_checks": {
                "no_passive_visual_only": True,
                "all_target_devices_interacted": True,
                "stale_data_ruled_out": True,
                "silent_errors_ruled_out": True
            },
            "verdict": "PASS"
        }
        res = validate_handoff_payload("acceptance", payload, strict_traceability=True)
        self.assertFalse(res["valid"])
        self.assertTrue(any("requirement_ids" in e for e in res["errors"]))

    def test_poai_missing_interactive_actions_rejected(self):
        """Negative Test 13: Passive inspection without click/tap/fill rejected."""
        payload = {
            "module": "Profile",
            "target_platforms": ["android:emulator-5554"],
            "fresh_test_identifier": "user_test_12345",
            "interactive_journey": [
                {"device": "emulator-5554", "action": "inspect screen passive look"}
            ],
            "state_mutation_delta": {"pre": "a", "post": "b"},
            "live_evidence": "logcat trace with sufficient length for validation",
            "anti_deception_checks": {
                "no_passive_visual_only": True,
                "all_target_devices_interacted": True,
                "stale_data_ruled_out": True,
                "silent_errors_ruled_out": True
            },
            "verdict": "PASS"
        }
        res = validate_handoff_payload("acceptance", payload)
        self.assertFalse(res["valid"])
        self.assertTrue(any("Proof-of-Active-Interaction Violation" in e for e in res["errors"]))


    def test_multi_device_blindspot_rejected(self):
        """Negative Test 14: Declaring dual platforms but only driving one is rejected."""
        payload = {
            "module": "P2PTransfer",
            "target_platforms": ["android:emulator-5554", "android:emulator-5556"],
            "fresh_test_identifier": "p2p_nonce_777",
            "interactive_journey": [
                # Only touches emulator-5554! emulator-5556 is omitted!
                {"device": "emulator-5554", "action": "tap #send_money"}
            ],
            "state_mutation_delta": {"pre": "unsent", "post": "sent"},
            "live_evidence": "Dual device logcat trace with sufficient chars",
            "anti_deception_checks": {
                "no_passive_visual_only": True,
                "all_target_devices_interacted": True,
                "stale_data_ruled_out": True,
                "silent_errors_ruled_out": True
            },
            "verdict": "PASS"
        }
        res = validate_handoff_payload("acceptance", payload)
        self.assertFalse(res["valid"])
        self.assertTrue(any("Multi-Device Blindspot Violation" in e for e in res["errors"]))


class TestNegativeWorktreeAndMemory(unittest.TestCase):
    """Negative tests for worktree merge safety and memory supersede protection."""

    def test_worktree_merge_rejected_when_working_tree_dirty(self):
        """Negative Test 15: Merge rejected if target repository has uncommitted changes."""
        with tempfile.TemporaryDirectory() as td:
            with patch("squad_engine.worktrees._run_git_cmd") as mock_git:
                # git status --porcelain returns modified file
                mock_git.return_value = MagicMock(stdout=" M dirty_file.py\n", returncode=0)
                result = merge_task_worktree(td, "feature_test")
            self.assertFalse(result["success"])
            self.assertIn("Dirty working tree", result["error"])

    def test_worktree_merge_rejected_when_test_command_fails(self):
        """Negative Test 16: Test-before-merge failure aborts merge."""
        with tempfile.TemporaryDirectory() as td:
            worktree_dir = Path(td) / ".worktrees" / "feature_test"
            worktree_dir.mkdir(parents=True)

            with patch("squad_engine.worktrees._run_git_cmd") as mock_git:
                # Clean working tree
                mock_git.return_value = MagicMock(stdout="", returncode=0)
                with patch("squad_engine.worktrees.subprocess.run") as mock_test:
                    # Test command exits with 1
                    mock_test.return_value = MagicMock(stderr="AssertionError: 1 != 2", returncode=1)
                    result = merge_task_worktree(td, "feature_test", test_command="pytest")
            self.assertFalse(result["success"])
            self.assertIn("Test-before-merge failed", result["error"])

    def test_memory_superseded_decision_excluded(self):
        """Negative Test 17: Superseded insight is excluded from active memory."""
        with tempfile.TemporaryDirectory() as td:
            mem = SquadMemory(workspace_path=td)
            # Add an old decision
            mem.append_long_term_insight("Auth Architecture", "Use custom JWT in cookies", trust_level="decision")
            # Mark it superseded
            count = mem.supersede_insight("Auth Architecture", reason="Replaced by Supabase Auth ADR-002")
            self.assertGreaterEqual(count, 1)

            # Active insights should NOT contain the superseded note
            active = mem.get_active_insights()
            self.assertNotIn("Use custom JWT in cookies", active)

            # Raw memory should retain the superseded history
            raw = mem.read_memory()
            self.assertIn("[SUPERSEDED]", raw)
            self.assertIn("Replaced by Supabase Auth ADR-002", raw)


if __name__ == "__main__":
    unittest.main()
