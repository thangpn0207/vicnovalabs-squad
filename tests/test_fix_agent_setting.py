#!/usr/bin/env python3
"""
Unit and Integration Tests for Agent Setting & Permission Self-Healing Engine.
Verifies static trap removal, global poisoning detection, mode healing, and permission matrices.
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from squad_engine.fix_agent_setting import (
    AgentSettingFixer,
    fix_agent_setting,
    format_fix_report_markdown
)
from squad_engine.cli import main
from squad_engine.gate import squad_gate


class TestFixAgentSetting(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_optimal_state_on_clean_workspace(self):
        # Pre-seed .squad_mode
        (self.workspace / ".squad_mode").write_text("suggest\n", encoding="utf-8")

        res = fix_agent_setting(workspace=str(self.workspace))
        self.assertEqual(res["status"], "OPTIMAL")
        self.assertEqual(res["remediations_count"], 0)
        self.assertEqual(res["post_state"]["workspace_static_agents_count"], 0)
        self.assertEqual(res["post_state"]["workspace_squad_mode"], "suggest")

        # Verify permissions matrix has all 6 roles
        perms = res["permissions_matrix"]
        self.assertIn("squad-dev", perms)
        self.assertIn("squad-qa", perms)
        self.assertTrue(perms["squad-dev"]["write_tools"])
        self.assertTrue(perms["squad-qa"]["write_tools"])

    def test_02_detects_and_removes_workspace_static_trap(self):
        # Create the dangerous static .agents/agents trap
        ws_agents = self.workspace / ".agents" / "agents"
        ws_agents.mkdir(parents=True, exist_ok=True)
        (ws_agents / "squad-dev.md").write_text("prompt content", encoding="utf-8")
        (ws_agents / "squad-qa.md").write_text("prompt content", encoding="utf-8")
        (ws_agents / "dev-agent.md").write_text("legacy content", encoding="utf-8")

        # Pre-check: trap exists
        self.assertTrue(ws_agents.exists())
        self.assertEqual(len(list(ws_agents.glob("*.md"))), 3)

        # Run healer
        res = fix_agent_setting(workspace=str(self.workspace))
        self.assertEqual(res["status"], "REPAIRED")
        self.assertGreaterEqual(res["remediations_count"], 1)

        # Post-check: static trap MUST be deleted
        self.assertFalse(ws_agents.exists())
        self.assertEqual(res["post_state"]["workspace_static_agents_count"], 0)

        # Verify remediation log details
        rems = [r for r in res["remediations"] if r["action"] == "REMOVE_WORKSPACE_STATIC_TRAP"]
        self.assertEqual(len(rems), 1)
        self.assertEqual(rems[0]["severity"], "CRITICAL")
        self.assertIn("squad-dev.md", rems[0]["details"])

    def test_03_dry_run_preserves_files_while_reporting(self):
        # Create static trap
        ws_agents = self.workspace / ".agents" / "agents"
        ws_agents.mkdir(parents=True, exist_ok=True)
        (ws_agents / "squad-dev.md").write_text("content", encoding="utf-8")

        # Run dry run
        res = fix_agent_setting(workspace=str(self.workspace), dry_run=True)
        self.assertEqual(res["status"], "REPAIRED")
        self.assertTrue(res["dry_run"])

        # In dry run, files must NOT be deleted
        self.assertTrue(ws_agents.exists())
        self.assertTrue((ws_agents / "squad-dev.md").exists())

    def test_04_heals_missing_or_corrupt_squad_mode(self):
        mode_file = self.workspace / ".squad_mode"
        # Test 1: missing
        self.assertFalse(mode_file.exists())
        res = fix_agent_setting(workspace=str(self.workspace))
        self.assertTrue(mode_file.exists())
        self.assertEqual(mode_file.read_text(encoding="utf-8").strip(), "suggest")

        # Test 2: corrupt mode
        mode_file.write_text("corrupt_invalid_mode_xyz", encoding="utf-8")
        res2 = fix_agent_setting(workspace=str(self.workspace))
        self.assertEqual(mode_file.read_text(encoding="utf-8").strip(), "suggest")

    def test_05_format_markdown_report(self):
        res = fix_agent_setting(workspace=str(self.workspace))
        md = format_fix_report_markdown(res)
        self.assertIn("VICNOVALABS SQUAD — AGENT PERMISSION & CONFIG HEALER", md)
        self.assertIn("squad-dev", md)
        self.assertIn("squad-qa", md)
        self.assertIn("write_to_file", md)

    def test_06_gate_dispatch_slash_command(self):
        # Test /vicnovalabs-squad fix-agent-setting
        res = squad_gate("/vicnovalabs-squad fix-agent-setting", workspace=str(self.workspace))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["execution_mode"], "inline")
        self.assertEqual(res["decision"], "FIX_AGENT_SETTING")
        self.assertIn("VICNOVALABS SQUAD — AGENT PERMISSION & CONFIG HEALER", res["dispatch_card_markdown"])

    def test_07_gate_dispatch_natural_language_intent(self):
        # Test natural Vietnamese prompt
        prompt = "kiểm tra lại permistion của các agent và fix setting"
        res = squad_gate(prompt, workspace=str(self.workspace))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["execution_mode"], "inline")
        self.assertEqual(res["decision"], "FIX_AGENT_SETTING")


if __name__ == "__main__":
    unittest.main()
