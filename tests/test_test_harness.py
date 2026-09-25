#!/usr/bin/env python3
"""
Unit tests for Test Harness Engine — verifying runner generation,
screenshot mutation, filesystem evidence, and exit code oracle.
"""

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from squad_engine.test_harness import (
    verify_screenshot_mutation,
    verify_filesystem_evidence,
    validate_exit_code_evidence,
    generate_test_runner_script,
    generate_mobile_runner,
    generate_web_runner,
)
from squad_engine.stack_detector import STACK_PROFILES


class TestScreenshotMutation(unittest.TestCase):
    def test_detects_identical_screenshots(self):
        """Identical pre/post screenshots should be flagged as UI_ACTION_FAILED."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre.png"
            post = Path(tmpdir) / "post.png"
            # Write identical content
            content = b"FAKE_PNG_IDENTICAL_CONTENT_12345"
            pre.write_bytes(content)
            post.write_bytes(content)

            result = verify_screenshot_mutation(str(pre), str(post))
            self.assertFalse(result["mutated"])
            self.assertEqual(result["pre_hash"], result["post_hash"])
            self.assertTrue(any("UI_ACTION_FAILED" in e for e in result["errors"]))

    def test_detects_different_screenshots(self):
        """Different pre/post screenshots should pass mutation check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pre = Path(tmpdir) / "pre.png"
            post = Path(tmpdir) / "post.png"
            pre.write_bytes(b"CONTENT_A_BEFORE_ACTION")
            post.write_bytes(b"CONTENT_B_AFTER_ACTION")

            result = verify_screenshot_mutation(str(pre), str(post))
            self.assertTrue(result["mutated"])
            self.assertNotEqual(result["pre_hash"], result["post_hash"])
            self.assertEqual(len(result["errors"]), 0)

    def test_missing_screenshot_files(self):
        """Missing screenshot files should be reported as errors."""
        result = verify_screenshot_mutation("/nonexistent/pre.png", "/nonexistent/post.png")
        self.assertFalse(result["mutated"])
        self.assertTrue(len(result["errors"]) >= 2)


class TestFilesystemEvidence(unittest.TestCase):
    def test_rejects_missing_files(self):
        """Missing evidence files should fail validation."""
        result = verify_filesystem_evidence(["/nonexistent/file.png", "/another/missing.txt"])
        self.assertFalse(result["valid"])
        self.assertEqual(result["found_files"], 0)
        self.assertTrue(any("missing" in e.lower() for e in result["errors"]))

    def test_rejects_empty_files(self):
        """Files smaller than 100 bytes should be flagged as suspicious."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tiny = Path(tmpdir) / "tiny.png"
            tiny.write_bytes(b"x")  # 1 byte

            result = verify_filesystem_evidence([str(tiny)])
            self.assertFalse(result["valid"])
            self.assertTrue(any("small" in e.lower() for e in result["errors"]))

    def test_accepts_valid_fresh_files(self):
        """Recent, non-trivial files should pass validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            good = Path(tmpdir) / "evidence.png"
            good.write_bytes(b"x" * 200)  # 200 bytes

            result = verify_filesystem_evidence([str(good)])
            self.assertTrue(result["valid"])
            self.assertEqual(result["found_files"], 1)
            self.assertEqual(len(result["errors"]), 0)

    def test_rejects_stale_files(self):
        """Files older than max_age_seconds should be flagged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old = Path(tmpdir) / "old.png"
            old.write_bytes(b"x" * 200)
            # Set modification time to 10 minutes ago
            old_time = os.path.getmtime(str(old)) - 600
            os.utime(str(old), (old_time, old_time))

            result = verify_filesystem_evidence([str(old)], max_age_seconds=300)
            self.assertFalse(result["valid"])
            self.assertTrue(any("stale" in e.lower() for e in result["errors"]))


class TestExitCodeOracle(unittest.TestCase):
    def test_rejects_nonzero_exit_code(self):
        """Non-zero exit code should always fail."""
        result = validate_exit_code_evidence(1)
        self.assertFalse(result["valid"])
        self.assertTrue(any("non-zero" in e.lower() for e in result["errors"]))

    def test_accepts_zero_exit_code(self):
        """Zero exit code with clean output should pass."""
        result = validate_exit_code_evidence(0, stdout="All tests passed.")
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)

    def test_detects_error_signatures_in_output(self):
        """Error signatures in stdout/stderr should be caught even with exit 0."""
        result = validate_exit_code_evidence(
            0, stdout="Test running...\nFATAL ERROR: segmentation fault"
        )
        self.assertFalse(result["valid"])
        self.assertTrue(len(result["error_signatures_found"]) > 0)

    def test_uses_stack_error_signatures(self):
        """Stack-specific error patterns should be detected."""
        flutter = STACK_PROFILES["flutter"]
        result = validate_exit_code_evidence(
            0,
            stdout="flutter: Unhandled Exception: NoSuchMethodError",
            stack=flutter
        )
        self.assertFalse(result["valid"])


class TestRunnerGeneration(unittest.TestCase):
    def test_mobile_runner_contains_adb(self):
        """Mobile runner should contain ADB commands."""
        script = generate_mobile_runner(
            package="com.example.app",
            device_serial="emulator-5554",
            steps=[{"action": "launch"}, {"action": "tap", "target": "100 200"}],
            evidence_dir="/tmp/test_evidence"
        )
        self.assertIn("adb", script)
        self.assertIn("emulator-5554", script)
        self.assertIn("com.example.app", script)
        self.assertIn("screencap", script)
        self.assertIn("assert_mutation", script)

    def test_web_runner_contains_playwright(self):
        """Web runner should contain Playwright commands."""
        script = generate_web_runner(
            url="http://localhost:3000",
            steps=[
                {"action": "navigate", "target": "http://localhost:3000"},
                {"action": "click", "target": "#submit"}
            ],
            evidence_dir="/tmp/test_web_evidence"
        )
        self.assertIn("playwright", script)
        self.assertIn("chromium.launch", script)
        self.assertIn("headless", script)
        self.assertIn("browser.close", script)
        self.assertIn("#submit", script)

    def test_generate_stack_adaptive_script(self):
        """generate_test_runner_script should adapt to stack category."""
        # Mobile stack
        flutter = STACK_PROFILES["flutter"]
        result = generate_test_runner_script(
            stack=flutter,
            journey_steps=[{"action": "launch"}],
            evidence_dir="/tmp/ev",
            package="com.test.app"
        )
        self.assertEqual(result["stack"], "flutter")
        self.assertIn("adb", result["script_content"])
        self.assertTrue(result["filename"].startswith("squad_runner_mobile_"))

        # Web stack
        web = STACK_PROFILES["web_frontend"]
        result_web = generate_test_runner_script(
            stack=web,
            journey_steps=[{"action": "navigate", "target": "http://localhost:3000"}],
            evidence_dir="/tmp/ev_web"
        )
        self.assertEqual(result_web["stack"], "web_frontend")
        self.assertIn("playwright", result_web["script_content"])
        self.assertTrue(result_web["filename"].startswith("squad_runner_web_"))

        # Backend stack
        python = STACK_PROFILES["python"]
        result_py = generate_test_runner_script(
            stack=python,
            journey_steps=[],
            evidence_dir="/tmp/ev_py"
        )
        self.assertEqual(result_py["stack"], "python")
        self.assertIn("pytest", result_py["script_content"])
        self.assertTrue(result_py["filename"].startswith("squad_runner_backend_"))

    def test_mobile_runner_contains_try_except(self):
        """Mobile runner should have error handling."""
        script = generate_mobile_runner(
            package="com.test",
            device_serial="emulator-5554",
            steps=[{"action": "launch"}],
            evidence_dir="/tmp/ev"
        )
        self.assertIn("try:", script)
        self.assertIn("except", script)
        self.assertIn("sys.exit(1)", script)
        self.assertIn("sys.exit(0)", script)

    def test_web_runner_contains_browser_close(self):
        """Web runner must close browser in finally block."""
        script = generate_web_runner(
            url="http://localhost:3000",
            steps=[{"action": "navigate", "target": "http://localhost:3000"}],
            evidence_dir="/tmp/ev"
        )
        self.assertIn("finally:", script)
        self.assertIn("browser.close()", script)


if __name__ == "__main__":
    unittest.main()
