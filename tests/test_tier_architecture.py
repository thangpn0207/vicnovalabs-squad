#!/usr/bin/env python3
"""
tests/test_tier_architecture.py
Verification suite for Squad Engine 3-Tier Execution Architecture:
- Tier 0: Passive Scanner (Zero-LLM/API, path/file matching, blast radius classifier)
- Tier 1: Manual On-Demand (/squad <role>, zero auto-chaining)
- Tier 2: Auto-Escalation (Soft suggestions, confirmed full pipeline)
- Rules Split: core-invariants.md (<500 tokens) vs execution-protocol.md
"""

import unittest
import os
from pathlib import Path
from squad_engine.passive_scanner import (
    run_passive_scanner,
    SIGNAL_GROUPS,
    SAFE_PATHS,
    NOTICE_TEMPLATES
)
from squad_engine.gate import squad_gate


class TestTier0PassiveScanner(unittest.TestCase):

    def test_css_and_markdown_only_is_always_fast_path(self):
        """A change touching only *.css or *.md never reaches escalate_suggested and produces zero notice."""
        cases = [
            ["src/theme.css"],
            ["styles/components/button.scss", "styles/grid.less"],
            ["README.md", "docs/spec.markdown"],
            ["assets/logo.png", "src/i18n/vi.json"]
        ]
        for files in cases:
            res = run_passive_scanner(touched_files=files, diff_lines_override=len(files) * 10)
            self.assertEqual(res.decision, "fast_path", f"Failed for {files}")
            self.assertIsNone(res.notice, f"Notice must be None for {files}")
            self.assertFalse(any(res.signals.values()), f"Signals must be False for {files}")

    def test_migrations_always_reaches_at_least_notify_only(self):
        """A change touching **/migrations/** always reaches at least notify_only or escalate_suggested."""
        # Small migration tweak (<= 5 lines) -> notify_only
        res_small = run_passive_scanner(
            touched_files=["db/migrations/001_create_users.sql"],
            diff_lines_override=4
        )
        self.assertEqual(res_small.decision, "notify_only")
        self.assertTrue(res_small.signals["database"])
        self.assertIn("schema/migration change detected", res_small.notice)

        # Standard migration change (> 5 lines) -> escalate_suggested
        res_standard = run_passive_scanner(
            touched_files=["db/migrations/002_add_index.sql"],
            diff_lines_override=25
        )
        self.assertEqual(res_standard.decision, "escalate_suggested")
        self.assertTrue(res_standard.signals["database"])
        self.assertIn("schema/migration change detected", res_standard.notice)

    def test_package_lock_patch_bump_is_notify_only(self):
        """A package-lock.json diff from a patch-version bump reaches notify_only, not escalate_suggested."""
        res = run_passive_scanner(
            touched_files=["package-lock.json"],
            diff_lines_override=12
        )
        self.assertEqual(res.decision, "notify_only")
        self.assertTrue(res.signals["dependency"])
        self.assertIn("dependency version change detected", res.notice)

    def test_ci_cd_file_shows_ci_cd_notice_template(self):
        """A CI/CD workflow file change shows the ci_cd notice template."""
        # Minor CI fix
        res_minor = run_passive_scanner(
            touched_files=[".github/workflows/deploy.yml"],
            diff_lines_override=6
        )
        self.assertEqual(res_minor.decision, "notify_only")
        self.assertTrue(res_minor.signals["ci_cd"])
        self.assertIn("CI/CD or infra config changed", res_minor.notice)

        # Larger CI change
        res_large = run_passive_scanner(
            touched_files=[".github/workflows/ci.yml", "Dockerfile"],
            diff_lines_override=40
        )
        self.assertEqual(res_large.decision, "escalate_suggested")
        self.assertTrue(res_large.signals["ci_cd"])
        self.assertIn("CI/CD or infra config changed", res_large.notice)

    def test_auth_security_always_reaches_escalate_suggested(self):
        """Auth/Security changes trigger escalate_suggested."""
        res = run_passive_scanner(
            touched_files=["src/auth/jwt_handler.py"],
            diff_lines_override=15
        )
        self.assertEqual(res.decision, "escalate_suggested")
        self.assertTrue(res.signals["auth_security"])
        self.assertIn("change touches Auth/Security", res.notice)


class TestTier1AndTier2Gate(unittest.TestCase):

    def test_squad_dev_alone_never_auto_chains(self):
        """Invoking /squad dev performs the dev task and stops — never auto-chains into QA."""
        prompts = [
            "/squad dev implement user profile screen",
            "squad dev fix login button styling",
            "/squad dev"
        ]
        for p in prompts:
            res = squad_gate(p, mode="suggest", touched_files=["src/profile.tsx"], diff_lines_override=20)
            self.assertEqual(res["role"], "dev")
            self.assertEqual(res["target_agent"], "squad-dev")
            self.assertFalse(res["auto_chain"], f"auto_chain must be False for {p}")
            self.assertIn("MANUAL_ON_DEMAND", res["decision"])

    def test_squad_full_runs_complete_pipeline(self):
        """/squad full still runs the complete pipeline unchanged with auto_chain == True."""
        prompts = [
            "/squad full build end-to-end checkout flow",
            "squad full run full verification",
            "run it through qa"
        ]
        for p in prompts:
            res = squad_gate(p, mode="suggest", touched_files=["src/checkout.py"], diff_lines_override=30)
            self.assertTrue(res["auto_chain"], f"auto_chain must be True for {p}")

    def test_squad_status_returns_mode_and_tier_0_scan_only(self):
        """/squad status returns current mode and last Tier 0 scan result, nothing else."""
        res = squad_gate("/squad status", mode="smart", touched_files=["src/app.py"], diff_lines_override=10)
        self.assertEqual(res["decision"], "STATUS")
        self.assertEqual(res["dispatch_mode"], "smart")
        self.assertIn("tier_0_scan", res)
        self.assertIn("signals", res["tier_0_scan"])
        self.assertIn("decision", res["tier_0_scan"])
        self.assertFalse(res["auto_chain"])

    def test_tier_2_soft_suggestion_does_not_force_pipeline(self):
        """Tier 2 soft suggestion remains inline unless confirmed or mode is auto."""
        # In suggest mode with migration change
        res = squad_gate(
            "run migration update",
            mode="suggest",
            touched_files=["db/migrations/003_billing.sql"],
            diff_lines_override=50
        )
        self.assertEqual(res["execution_mode"], "inline")
        self.assertFalse(res["auto_chain"])
        self.assertIsNotNone(res.get("soft_suggestion"))
        self.assertIn("schema/migration change detected", res["soft_suggestion"])

        # In auto mode with migration change
        res_auto = squad_gate(
            "run migration update",
            mode="auto",
            touched_files=["db/migrations/003_billing.sql"],
            diff_lines_override=50
        )
        self.assertEqual(res_auto["execution_mode"], "subagent")
        self.assertTrue(res_auto["auto_chain"])


class TestRulesFileSplit(unittest.TestCase):

    def test_core_invariants_token_size_is_under_500_tokens(self):
        """Verify that core-invariants.md stays under 500 tokens (~2000 chars)."""
        core_path = Path(__file__).parent.parent / "rules" / "core-invariants.md"
        self.assertTrue(core_path.exists(), "rules/core-invariants.md must exist")
        text = core_path.read_text(encoding="utf-8")
        est_tokens = int(len(text) / 3.8)
        self.assertLess(est_tokens, 500, f"Token count {est_tokens} exceeded 500 tokens limit")

    def test_core_invariants_contains_essential_governance_rules(self):
        """Verify core invariants contains coding invariants and output discipline."""
        core_path = Path(__file__).parent.parent / "rules" / "core-invariants.md"
        text = core_path.read_text(encoding="utf-8")
        self.assertIn("Never hardcode secrets", text)
        self.assertIn("Never bypass existing authentication", text)
        self.assertIn("[RESULT]", text)
        self.assertIn("Output Discipline", text)

    def test_execution_protocol_file_exists(self):
        """Verify that execution-protocol.md exists and contains handoff schemas and torture dimensions."""
        exec_path = Path(__file__).parent.parent / "rules" / "execution-protocol.md"
        self.assertTrue(exec_path.exists(), "rules/execution-protocol.md must exist")
        text = exec_path.read_text(encoding="utf-8")
        self.assertIn("HandoffManifest", text)
        self.assertIn("SignoffReceipt", text)
        self.assertIn("Torture Dimension", text)


if __name__ == "__main__":
    unittest.main()
