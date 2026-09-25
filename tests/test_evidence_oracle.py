#!/usr/bin/env python3
"""
Unit tests for External Anti-Fraud Oracle (evidence_oracle.py).
Tests evidence bundle validation, runner result parsing, and anti-fraud detection.
"""

import hashlib
import os
import tempfile
import time
import unittest
from pathlib import Path

from squad_engine.evidence_oracle import (
    validate_evidence_bundle,
    validate_runner_result,
)
from squad_engine.stack_detector import STACK_PROFILES


class TestValidateEvidenceBundle(unittest.TestCase):
    def test_rejects_nonexistent_directory(self):
        """Non-existent evidence directory should fail."""
        result = validate_evidence_bundle("/nonexistent/evidence/dir")
        self.assertFalse(result["valid"])
        self.assertTrue(any("does not exist" in e for e in result["errors"]))

    def test_rejects_empty_directory(self):
        """Empty evidence directory should fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_evidence_bundle(tmpdir)
            self.assertFalse(result["valid"])
            self.assertTrue(any("empty" in e.lower() for e in result["errors"]))

    def test_rejects_identical_pre_post_screenshots(self):
        """Identical pre/post screenshots indicate UI action failed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            content = b"FAKE_SCREENSHOT_IDENTICAL" * 500  # > 10KB
            Path(tmpdir, "step_01_pre.png").write_bytes(content)
            Path(tmpdir, "step_01_post.png").write_bytes(content)

            result = validate_evidence_bundle(tmpdir)
            self.assertFalse(result["valid"])
            self.assertTrue(any("UI_ACTION_FAILED" in e for e in result["errors"]))
            self.assertFalse(result["mutation_verified"])

    def test_accepts_mutated_screenshots(self):
        """Different pre/post screenshots should pass mutation check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "step_01_pre.png").write_bytes(b"BEFORE_STATE" * 1000)
            Path(tmpdir, "step_01_post.png").write_bytes(b"AFTER_STATE_DIFFERENT" * 1000)

            result = validate_evidence_bundle(tmpdir)
            self.assertTrue(result["valid"])
            self.assertTrue(result["mutation_verified"])
            self.assertEqual(len(result["screenshot_pairs"]), 1)
            self.assertTrue(result["screenshot_pairs"][0]["mutated"])

    def test_detects_error_in_log_files(self):
        """Error signatures in log files should be reported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # A valid screenshot pair
            Path(tmpdir, "step_01_pre.png").write_bytes(b"BEFORE" * 2000)
            Path(tmpdir, "step_01_post.png").write_bytes(b"AFTER_DIFF" * 2000)
            # A log file with errors
            Path(tmpdir, "logcat_errors.txt").write_text(
                "FATAL ERROR: NullPointerException at line 42"
            )

            result = validate_evidence_bundle(tmpdir)
            self.assertFalse(result["valid"])
            self.assertTrue(any("Error signature" in e for e in result["errors"]))

    def test_warns_on_small_screenshots(self):
        """Screenshots under 10KB should generate warnings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "screenshot.png").write_bytes(b"tiny" * 100)  # 400 bytes

            result = validate_evidence_bundle(tmpdir)
            self.assertTrue(len(result["warnings"]) > 0)
            self.assertTrue(any("small" in w.lower() for w in result["warnings"]))

    def test_warns_on_stale_evidence(self):
        """Evidence files older than max_age should generate warnings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir, "old_evidence.png")
            f.write_bytes(b"X" * 20000)
            # Set modification time to 10 minutes ago
            old_time = time.time() - 600
            os.utime(str(f), (old_time, old_time))

            result = validate_evidence_bundle(tmpdir, max_age_seconds=300)
            self.assertTrue(len(result["warnings"]) > 0)
            self.assertTrue(any("stale" in w.lower() for w in result["warnings"]))

    def test_detects_stack_specific_errors(self):
        """Stack-specific error signatures should be detected in logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "output.txt").write_text(
                "flutter: Unhandled Exception: type 'Null' is not a subtype"
            )
            Path(tmpdir, "step_01_pre.png").write_bytes(b"A" * 20000)
            Path(tmpdir, "step_01_post.png").write_bytes(b"B" * 20000)

            flutter = STACK_PROFILES["flutter"]
            result = validate_evidence_bundle(tmpdir, stack=flutter)
            self.assertFalse(result["valid"])

    def test_multiple_step_pairs(self):
        """Multiple pre/post screenshot pairs should all be checked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: mutated
            Path(tmpdir, "step_01_pre.png").write_bytes(b"A" * 20000)
            Path(tmpdir, "step_01_post.png").write_bytes(b"B" * 20000)
            # Step 2: identical
            content = b"C" * 20000
            Path(tmpdir, "step_02_pre.png").write_bytes(content)
            Path(tmpdir, "step_02_post.png").write_bytes(content)

            result = validate_evidence_bundle(tmpdir)
            self.assertFalse(result["valid"])  # Step 2 failed
            self.assertEqual(len(result["screenshot_pairs"]), 2)


class TestValidateRunnerResult(unittest.TestCase):
    def test_rejects_nonzero_exit(self):
        """Non-zero exit code should fail validation."""
        result = validate_runner_result("some output", exit_code=1)
        self.assertFalse(result["valid"])
        self.assertTrue(any("code 1" in e for e in result["errors"]))

    def test_accepts_zero_exit_with_success_marker(self):
        """Exit 0 with success marker should pass."""
        result = validate_runner_result("=== ALL STEPS PASSED ===", exit_code=0)
        self.assertTrue(result["valid"])
        self.assertTrue(result["has_success_marker"])

    def test_detects_failure_markers(self):
        """Failure markers in output should be caught."""
        result = validate_runner_result(
            "RUNNER_EXCEPTION: Connection refused\n=== FAILURES (1) ===",
            exit_code=1
        )
        self.assertFalse(result["valid"])
        self.assertTrue(any("Failure marker" in e for e in result["errors"]))

    def test_warns_on_zero_exit_without_success(self):
        """Exit 0 but no success marker should generate warning."""
        result = validate_runner_result("some ambiguous output", exit_code=0)
        self.assertTrue(result["valid"])  # Still passes (exit 0)
        self.assertTrue(len(result["warnings"]) > 0)

    def test_detects_stack_errors(self):
        """Stack-specific error patterns should be detected."""
        go_stack = STACK_PROFILES["go"]
        result = validate_runner_result(
            "goroutine 1 [running]:\npanic: runtime error",
            exit_code=0,
            stack=go_stack
        )
        self.assertFalse(result["valid"])


if __name__ == "__main__":
    unittest.main()
