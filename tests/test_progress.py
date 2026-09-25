#!/usr/bin/env python3
"""
Unit tests for Project Progress Tracker.
"""

import unittest
import tempfile
from pathlib import Path
from squad_engine.progress import parse_project_progress, init_project_progress


class TestProjectProgress(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_init_and_parse_progress(self):
        test_file = self.tmp_path / "PROJECT_PROGRESS.md"
        tasks = ["Setup auth", "Implement payment API", "Write e2e tests"]

        init_res = init_project_progress("Payment Gateway", tasks, str(test_file))
        self.assertEqual(init_res["status"], "INITIALIZED")
        self.assertEqual(init_res["total_tasks"], 3)
        self.assertTrue(test_file.exists())

        parse_res = parse_project_progress(str(test_file))
        self.assertEqual(parse_res["status"], "TRACKED")
        self.assertEqual(parse_res["total_tasks"], 3)
        self.assertEqual(parse_res["completed_tasks"], 0)
        self.assertEqual(parse_res["pending_tasks"], 3)
        self.assertEqual(parse_res["progress_percentage"], 0.0)

    def test_parse_with_completed_and_qa_tasks(self):
        test_file = self.tmp_path / "PROGRESS_MOCK.md"
        content = """# Feature Tracker
| Module | Status | Notes |
| :--- | :---: | :--- |
| Auth | `[x] DONE` | Verified |
| API | `[-] READY_FOR_QA` | Handoff manifest ready |
| UI | `[ ] PENDING` | Not started |

## 4. Đề xuất Bước Kế tiếp
1. Chạy nghiệm thu Playwright cho API
"""
        test_file.write_text(content, encoding="utf-8")
        res = parse_project_progress(str(test_file))
        self.assertEqual(res["total_tasks"], 3)
        self.assertEqual(res["completed_tasks"], 1)
        self.assertEqual(res["in_progress_tasks"], 1)
        self.assertEqual(res["ready_for_qa_tasks"], 1)
        self.assertEqual(res["pending_tasks"], 1)
        self.assertEqual(res["progress_percentage"], 33.3)
        self.assertIn("Playwright", res["next_recommended_action"])

    def test_orchestrator_defect_loopback_escalation(self):
        from squad_engine.orchestrator import SquadOrchestrator
        orch = SquadOrchestrator(workspace_path=str(self.tmp_path))
        test_file = self.tmp_path / "PROJECT_PROGRESS.md"
        test_file.write_text("- [-] READY_FOR_QA `Auth`\n", encoding="utf-8")

        defect_payload = {
            "ticket_id": "DEF-001",
            "module": "Auth",
            "severity": "Blocker",
            "repro_steps": ["Click login"],
            "target_selector_or_screen": "#btn",
            "actual_behavior": "Fails",
            "expected_behavior": "Passes",
            "logs_or_stacktrace": "NullPointer",
            "visual_diff_score": 0.0
        }

        # Attempt 1: Returns DISPATCH_DEV_BUGFIX
        res1 = orch.handle_defect(defect_payload)
        self.assertTrue(res1["success"])
        self.assertEqual(res1["action"], "DISPATCH_DEV_BUGFIX")
        self.assertEqual(res1["attempt"], 1)

        # Attempt 2: Returns DISPATCH_DEV_BUGFIX
        res2 = orch.handle_defect(defect_payload)
        self.assertTrue(res2["success"])
        self.assertEqual(res2["action"], "DISPATCH_DEV_BUGFIX")
        self.assertEqual(res2["attempt"], 2)

        # Attempt 3: Exceeds MAX_DEFECT_LOOPBACKS (2) -> ESCALATE_TO_HUMAN
        res3 = orch.handle_defect(defect_payload)
        self.assertFalse(res3["success"])
        self.assertEqual(res3["action"], "ESCALATE_TO_HUMAN")
        self.assertTrue(res3["stop_required"])
        self.assertIn("Escalating to human user", res3["message"])


if __name__ == "__main__":
    unittest.main()

