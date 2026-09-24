#!/usr/bin/env python3
"""
Unit tests for Squad Dispatch Mode Manager & Scoping (Project vs Non-Project Session).
"""

import os
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from squad_engine.mode import (
    detect_project_workspace,
    detect_session_id,
    get_session_mode_file,
    get_effective_dispatch_mode,
    set_dispatch_mode,
    handle_squad_mode_prompt,
    VALID_MODES
)
from squad_engine.gate import squad_gate


class TestSquadMode(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="squad_test_mode_")
        self.proj_dir = Path(self.temp_dir) / "test_project"
        self.proj_dir.mkdir(parents=True)
        (self.proj_dir / "PROJECT_PROGRESS.md").write_text("# Test Progress\n", encoding="utf-8")

        self.non_proj_dir = Path(self.temp_dir) / "not_a_project"
        self.non_proj_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_detect_project_workspace(self):
        # Inside project
        detected = detect_project_workspace(str(self.proj_dir))
        self.assertIsNotNone(detected)
        self.assertEqual(detected.resolve(), self.proj_dir.resolve())

        # Subdirectory of project
        sub_dir = self.proj_dir / "src" / "deep"
        sub_dir.mkdir(parents=True)
        detected_sub = detect_project_workspace(str(sub_dir))
        self.assertIsNotNone(detected_sub)
        self.assertEqual(detected_sub.resolve(), self.proj_dir.resolve())

        # Non-project directory
        detected_non = detect_project_workspace(str(self.non_proj_dir))
        self.assertIsNone(detected_non)

    def test_default_mode_project_is_suggest(self):
        info = get_effective_dispatch_mode(workspace=str(self.proj_dir))
        self.assertEqual(info["mode"], "suggest")
        self.assertEqual(info["source"], "default_project")
        self.assertTrue(info["is_project"])

    def test_default_mode_non_project_is_inline(self):
        # Outside of a project, default priority MUST be inline
        info = get_effective_dispatch_mode(workspace=str(self.non_proj_dir), session_id="test_sess_default")
        self.assertEqual(info["mode"], "inline")
        self.assertEqual(info["source"], "default_non_project")
        self.assertFalse(info["is_project"])

    def test_set_mode_project_persists_to_file(self):
        # Set to smart in project
        res = set_dispatch_mode("smart", workspace=str(self.proj_dir))
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["target"], "project")

        # Verify .squad_mode was written
        mode_file = self.proj_dir / ".squad_mode"
        self.assertTrue(mode_file.exists())
        self.assertEqual(mode_file.read_text().strip(), "smart")

        # Now get_effective_dispatch_mode should return smart from project
        info = get_effective_dispatch_mode(workspace=str(self.proj_dir))
        self.assertEqual(info["mode"], "smart")
        self.assertEqual(info["source"], "project")

    def test_set_mode_non_project_session_persists_to_session(self):
        sess_id = "custom_session_999"
        res = set_dispatch_mode("auto", workspace=str(self.non_proj_dir), session_id=sess_id)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["target"], "session")
        self.assertEqual(res["session_id"], sess_id)

        # Mode for this session should now be auto
        info = get_effective_dispatch_mode(workspace=str(self.non_proj_dir), session_id=sess_id)
        self.assertEqual(info["mode"], "auto")
        self.assertEqual(info["source"], "session")

        # Another session in the same non-project directory still defaults to inline
        other_info = get_effective_dispatch_mode(workspace=str(self.non_proj_dir), session_id="other_session_000")
        self.assertEqual(other_info["mode"], "inline")
        self.assertEqual(other_info["source"], "default_non_project")

    def test_handle_squad_mode_prompt_queries(self):
        # /vicnolabs-squad mode
        res1 = handle_squad_mode_prompt("/vicnolabs-squad mode", workspace=str(self.proj_dir))
        self.assertIsNotNone(res1)
        self.assertEqual(res1["decision"], "QUERY_SQUAD_MODE")
        self.assertIn("Current Mode", res1["dispatch_card_markdown"])

        # /vicnovalabs-squad
        res2 = handle_squad_mode_prompt("/vicnovalabs-squad", workspace=str(self.proj_dir))
        self.assertIsNotNone(res2)
        self.assertEqual(res2["decision"], "QUERY_SQUAD_MODE")

        # /squad mode
        res3 = handle_squad_mode_prompt("/squad mode", workspace=str(self.proj_dir))
        self.assertIsNotNone(res3)
        self.assertEqual(res3["decision"], "QUERY_SQUAD_MODE")

    def test_handle_squad_mode_prompt_setting(self):
        # /vicnolabs-squad smart
        res = handle_squad_mode_prompt("/vicnolabs-squad smart", workspace=str(self.proj_dir))
        self.assertIsNotNone(res)
        self.assertEqual(res["decision"], "SET_SQUAD_MODE")
        self.assertEqual(res["mode"], "smart")
        self.assertEqual(res["target"], "project")

        # Verify via gate
        gate_res = squad_gate("/vicnolabs-squad auto", workspace=str(self.proj_dir))
        self.assertEqual(gate_res["decision"], "SET_SQUAD_MODE")
        self.assertEqual(gate_res["mode"], "auto")

    def test_gate_interception_for_session(self):
        # Set mode in non-project session via gate
        sess_id = "sess_gate_test_1"
        res = squad_gate(
            "/vicnolabs-squad mode smart",
            workspace=str(self.non_proj_dir)
        )
        self.assertEqual(res["decision"], "SET_SQUAD_MODE")
        self.assertEqual(res["mode"], "smart")
        self.assertEqual(res["target"], "session")


if __name__ == "__main__":
    unittest.main()
