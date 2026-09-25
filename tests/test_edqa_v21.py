#!/usr/bin/env python3
"""
EDQA v2.1 — Unit tests for all improvements across:
  P1-A: SSRF protection in crawler
  P1-B: TLS verify_tls param
  P1-C: Flexible screenshot mutation detection
  P1-D: Memory trust tagging & compact_memory
  P2-A: ADB preflight function exists and returns correct structure
  P2-B: Defect count persistence (load/save)
  P2-C: signoff schema alias
  P2-D: Runner script auto-write to disk
  P3-A: Strict success marker regex
  P3-C: File lock utility
  P4-A: orchestrate_pipeline signature cleaned
"""

import hashlib
import inspect
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestSSRFProtection(unittest.TestCase):
    """P1-A: SSRF block list in crawler.py"""

    def test_localhost_blocked(self):
        from squad_engine.crawler import _is_ssrf_blocked
        self.assertTrue(_is_ssrf_blocked("http://localhost/api"))

    def test_loopback_ip_blocked(self):
        from squad_engine.crawler import _is_ssrf_blocked
        self.assertTrue(_is_ssrf_blocked("http://127.0.0.1:8080/"))

    def test_private_class_a_blocked(self):
        from squad_engine.crawler import _is_ssrf_blocked
        self.assertTrue(_is_ssrf_blocked("http://10.0.0.1/secret"))

    def test_private_class_c_blocked(self):
        from squad_engine.crawler import _is_ssrf_blocked
        self.assertTrue(_is_ssrf_blocked("http://192.168.1.1/admin"))

    def test_aws_metadata_blocked(self):
        from squad_engine.crawler import _is_ssrf_blocked
        self.assertTrue(_is_ssrf_blocked("http://169.254.169.254/latest/meta-data/"))

    def test_crawl_blocked_returns_blocked_status(self):
        from squad_engine.crawler import crawl_url_to_markdown
        result = crawl_url_to_markdown("http://localhost:3000/")
        self.assertEqual(result["status"], "blocked")
        self.assertIn("SSRF_PROTECTION", result["error"])
        self.assertEqual(result["markdown"], "")


class TestTLSVerification(unittest.TestCase):
    """P1-B: TLS verify_tls param defaults to True"""

    def test_verify_tls_param_exists(self):
        from squad_engine.crawler import crawl_url_to_markdown
        sig = inspect.signature(crawl_url_to_markdown)
        self.assertIn("verify_tls", sig.parameters)
        self.assertEqual(sig.parameters["verify_tls"].default, True)


class TestFlexibleScreenshotMutation(unittest.TestCase):
    """P1-C: Flexible pre/post mutation detection strategies"""

    def _write_png(self, path: Path, content: bytes):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def test_strategy_a_canonical_pattern(self):
        from squad_engine.evidence_oracle import validate_evidence_bundle
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            self._write_png(d / "step_01_pre.png", b"A" * 15000)
            self._write_png(d / "step_01_post.png", b"B" * 15000)
            result = validate_evidence_bundle(td)
        self.assertTrue(result["mutation_verified"])
        self.assertTrue(any(p["strategy"] == "canonical" for p in result["screenshot_pairs"]))

    def test_strategy_b_before_after_naming(self):
        from squad_engine.evidence_oracle import validate_evidence_bundle
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            self._write_png(d / "screen_before.png", b"C" * 15000)
            self._write_png(d / "screen_after.png", b"D" * 15000)
            result = validate_evidence_bundle(td)
        self.assertTrue(result["mutation_verified"])
        self.assertTrue(any(p["strategy"] == "before_after" for p in result["screenshot_pairs"]))

    def test_strategy_c_chronological_fallback(self):
        from squad_engine.evidence_oracle import validate_evidence_bundle
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            self._write_png(d / "screenshot_a.png", b"E" * 15000)
            time.sleep(0.05)
            self._write_png(d / "screenshot_b.png", b"F" * 15000)
            result = validate_evidence_bundle(td)
        self.assertTrue(result["mutation_verified"])
        self.assertTrue(any(p["strategy"] == "chronological" for p in result["screenshot_pairs"]))

    def test_identical_screenshots_fail_mutation(self):
        from squad_engine.evidence_oracle import validate_evidence_bundle
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            content = b"X" * 15000
            self._write_png(d / "step_01_pre.png", content)
            self._write_png(d / "step_01_post.png", content)
            result = validate_evidence_bundle(td)
        self.assertFalse(result["mutation_verified"])
        self.assertTrue(any("UI_ACTION_FAILED" in e for e in result["errors"]))


class TestMemoryTrustTagging(unittest.TestCase):
    """P1-D: Memory trust level tagging and compact_memory"""

    def test_verified_tag_on_insight(self):
        from squad_engine.memory import SquadMemory
        with tempfile.TemporaryDirectory() as td:
            mem = SquadMemory(workspace_path=td)
            mem.append_long_term_insight("DB schema", "Use UUIDs", trust_level="verified")
            content = mem.read_memory()
        self.assertIn("[VERIFIED]", content)

    def test_inferred_tag_default(self):
        from squad_engine.memory import SquadMemory
        with tempfile.TemporaryDirectory() as td:
            mem = SquadMemory(workspace_path=td)
            mem.append_long_term_insight("Agent note", "Probably REST")
            content = mem.read_memory()
        self.assertIn("[INFERRED]", content)

    def test_compact_memory_removes_old_inferred(self):
        from squad_engine.memory import SquadMemory
        with tempfile.TemporaryDirectory() as td:
            mem = SquadMemory(workspace_path=td)
            for i in range(5):
                mem.append_long_term_insight(f"Inferred {i}", f"Text {i}", trust_level="inferred")
            mem.append_long_term_insight("Proven fact", "Oracle confirmed", trust_level="verified")
            result = mem.compact_memory(max_inferred_entries=3)
        self.assertTrue(result["compacted"])
        self.assertEqual(result["removed_entries"], 2)
        self.assertEqual(result["remaining_inferred"], 3)


class TestADBPreflight(unittest.TestCase):
    """P2-A: run_adb_preflight function exists and returns correct structure"""

    def test_preflight_function_exists(self):
        from squad_engine.devices import run_adb_preflight
        self.assertTrue(callable(run_adb_preflight))

    def test_preflight_returns_required_keys(self):
        from squad_engine.devices import run_adb_preflight
        with patch("squad_engine.devices.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="__ok__", returncode=0)
            result = run_adb_preflight("emulator-5554")
        for key in ("ready", "checks", "errors", "serial"):
            self.assertIn(key, result)

    def test_preflight_detects_responsive_device(self):
        from squad_engine.devices import run_adb_preflight
        with patch("squad_engine.devices.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="__ok__", returncode=0)
            result = run_adb_preflight("emulator-5554")
        self.assertTrue(result["checks"].get("device_responsive"))

    def test_preflight_fails_on_unresponsive_device(self):
        from squad_engine.devices import run_adb_preflight
        with patch("squad_engine.devices.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=1)
            result = run_adb_preflight("emulator-5554")
        self.assertFalse(result["ready"])
        self.assertTrue(len(result["errors"]) > 0)


class TestDefectCountPersistence(unittest.TestCase):
    """P2-B: Defect counts persist across SquadOrchestrator instantiations"""

    def test_defect_counts_loaded_from_progress_md(self):
        from squad_engine.orchestrator import SquadOrchestrator
        with tempfile.TemporaryDirectory() as td:
            progress = Path(td) / "PROJECT_PROGRESS.md"
            progress.write_text("# Test\n\n<!-- defect_counts: {\"ModuleA\": 2} -->\n")
            orch = SquadOrchestrator(workspace_path=td)
        self.assertEqual(orch.defect_counts.get("ModuleA"), 2)

    def test_defect_counts_persisted(self):
        from squad_engine.orchestrator import SquadOrchestrator
        with tempfile.TemporaryDirectory() as td:
            progress = Path(td) / "PROJECT_PROGRESS.md"
            progress.write_text("# Test\n")
            orch = SquadOrchestrator(workspace_path=td)
            orch.defect_counts["ModuleB"] = 1
            orch._persist_defect_counts()
            content = progress.read_text()
        self.assertIn("ModuleB", content)
        self.assertIn("defect_counts", content)

    def test_defect_count_survives_reinstantiation(self):
        from squad_engine.orchestrator import SquadOrchestrator
        with tempfile.TemporaryDirectory() as td:
            progress = Path(td) / "PROJECT_PROGRESS.md"
            progress.write_text("# Test\n")
            orch1 = SquadOrchestrator(workspace_path=td)
            orch1.defect_counts["Feature-X"] = 1
            orch1._persist_defect_counts()
            orch2 = SquadOrchestrator(workspace_path=td)
        self.assertEqual(orch2.defect_counts.get("Feature-X"), 1)


class TestSignoffAlias(unittest.TestCase):
    """P2-C: signoff schema is an alias for acceptance"""

    def test_signoff_alias_exists(self):
        from squad_engine.handoffs import TYPED_HANDOFF_SCHEMAS
        self.assertIn("signoff", TYPED_HANDOFF_SCHEMAS)

    def test_signoff_same_object_as_acceptance(self):
        from squad_engine.handoffs import TYPED_HANDOFF_SCHEMAS
        self.assertIs(TYPED_HANDOFF_SCHEMAS["signoff"], TYPED_HANDOFF_SCHEMAS["acceptance"])


class TestRunnerAutoWrite(unittest.TestCase):
    """P2-D: generate_test_runner_script auto-writes script to disk"""

    def test_runner_script_written_to_disk(self):
        from squad_engine.test_harness import generate_test_runner_script
        from squad_engine.stack_detector import STACK_PROFILES
        with tempfile.TemporaryDirectory() as td:
            stack = STACK_PROFILES["python"]
            result = generate_test_runner_script(
                stack=stack,
                journey_steps=[],
                evidence_dir=f"{td}/evidence",
                output_dir=f"{td}/test"
            )
            exists = Path(result["script_path"]).exists() if result.get("script_path") else False
        self.assertIsNotNone(result.get("script_path"))
        self.assertTrue(exists)


    def test_script_path_in_result(self):
        from squad_engine.test_harness import generate_test_runner_script
        sig = inspect.signature(generate_test_runner_script)
        # output_dir param should exist
        self.assertIn("output_dir", sig.parameters)


class TestSuccessMarkerRegex(unittest.TestCase):
    """P3-A: Strict success marker detection"""

    def test_squad_harness_matches(self):
        from squad_engine.evidence_oracle import validate_runner_result
        output = "Step 1\nStep 2\n\n=== ALL STEPS PASSED ==="
        result = validate_runner_result(output, exit_code=0)
        self.assertTrue(result["has_success_marker"])

    def test_unittest_ok_matches(self):
        from squad_engine.evidence_oracle import validate_runner_result
        output = "......\n----------------------------------------------------------------------\nRan 5 tests in 0.1s\n\nOK"
        result = validate_runner_result(output, exit_code=0)
        self.assertTrue(result["has_success_marker"])

    def test_pytest_matches(self):
        from squad_engine.evidence_oracle import validate_runner_result
        output = "collected 10 items\n\n10 passed in 1.23s"
        result = validate_runner_result(output, exit_code=0)
        self.assertTrue(result["has_success_marker"])

    def test_failed_exit_code_fails_validation(self):
        from squad_engine.evidence_oracle import validate_runner_result
        result = validate_runner_result("", exit_code=1)
        self.assertFalse(result["valid"])


class TestFileLocking(unittest.TestCase):
    """P3-C: _write_with_lock works correctly"""

    def test_file_written_correctly(self):
        from squad_engine.progress import _write_with_lock
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.md"
            _write_with_lock(p, "Hello World")
            self.assertEqual(p.read_text(), "Hello World")


class TestOrchestratePipelineCleanSignature(unittest.TestCase):
    """P4-A: orchestrate_pipeline no longer has dead params"""

    def test_dead_params_removed(self):
        from squad_engine.orchestrator import orchestrate_pipeline
        sig = inspect.signature(orchestrate_pipeline)
        self.assertNotIn("last_status", sig.parameters)
        self.assertNotIn("defect_ticket", sig.parameters)
        self.assertNotIn("progress_file", sig.parameters)

    def test_valid_params_remain(self):
        from squad_engine.orchestrator import orchestrate_pipeline
        sig = inspect.signature(orchestrate_pipeline)
        self.assertIn("user_prompt", sig.parameters)
        self.assertIn("platform", sig.parameters)
        self.assertIn("workspace", sig.parameters)


if __name__ == "__main__":
    unittest.main()
