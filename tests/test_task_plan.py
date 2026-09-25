#!/usr/bin/env python3
"""
Unit tests for Scoped Task Plan Engine, partitioning, and Barrier Sync.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from squad_engine.task_plan import (
    init_scoped_task_plan,
    parse_scoped_task_plan,
    update_scoped_task_plan,
    reconcile_scoped_task_plan,
    prune_scoped_plans,
    decompose_large_task,
    is_composite_or_large_task,
    is_single_task
)


class TestTaskPlan(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_single_task_detection(self):
        self.assertTrue(is_single_task("chỉ sửa 1 typo trong readme"))
        self.assertTrue(is_single_task("giải thích đoạn code này"))
        self.assertFalse(is_single_task("triển khai toàn bộ màn hình thanh toán và settings"))

    def test_composite_task_detection(self):
        self.assertTrue(is_composite_or_large_task("kiểm thử toàn bộ hệ thống pairing và chat"))
        self.assertTrue(is_composite_or_large_task("batch test all screens song song"))
        self.assertFalse(is_composite_or_large_task("chỉ sửa 1 lỗi nhỏ"))

    def test_task_plan_lifecycle(self):
        # 1. Init
        init_res = init_scoped_task_plan(
            title="E2E Checkout Flow",
            subtasks=["Cart Validation", "Payment Gateway"],
            partition_strategy="DISJOINT_MODULES",
            workspace=self.test_dir
        )
        self.assertEqual(init_res["status"], "success")
        self.assertEqual(init_res["total_subtasks"], 2)

        plan_path = init_res["file_path"]
        self.assertTrue(Path(plan_path).exists())

        # 2. Parse initial
        parse_res = parse_scoped_task_plan(plan_path, workspace=self.test_dir)
        self.assertEqual(parse_res["completed_count"], 0)
        self.assertEqual(parse_res["progress_percent"], 0)
        self.assertFalse(parse_res["is_completed"])

        # 3. Update Subtask ST-01
        up_res = update_scoped_task_plan(
            plan_file=plan_path,
            subtask_id="ST-01",
            status="DONE",
            note="Cart tests passed",
            workspace=self.test_dir
        )
        self.assertEqual(up_res["status"], "success")
        self.assertEqual(up_res["progress_percent"], 50)
        self.assertFalse(up_res["is_all_completed"])

        # 4. Update Subtask ST-02 -> Completed
        up_res2 = update_scoped_task_plan(
            plan_file=plan_path,
            subtask_id="ST-02",
            status="DONE",
            note="Payment verified",
            workspace=self.test_dir
        )
        self.assertEqual(up_res2["progress_percent"], 100)
        self.assertTrue(up_res2["is_all_completed"])

        # 5. Reconcile with root progress
        fake_progress = Path(self.test_dir) / "PROJECT_PROGRESS.md"
        fake_progress.write_text(
            "# Progress\n- [ ] `Cart Validation`\n- [ ] `Payment Gateway`\n",
            encoding="utf-8"
        )
        rec_res = reconcile_scoped_task_plan(
            plan_file=plan_path,
            progress_file=str(fake_progress),
            workspace=self.test_dir
        )
        self.assertEqual(rec_res["status"], "success")
        self.assertTrue(rec_res["all_subtasks_done"])
        self.assertIn("- [x] `Cart Validation`", fake_progress.read_text(encoding="utf-8"))

    def test_prune_scoped_plans(self):
        plans_dir = Path(self.test_dir) / ".agents" / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        # Create 12 dummy plan files
        for i in range(12):
            p = plans_dir / f"TASK_PLAN_test_{i:02d}_20260925_0000{i:02d}.md"
            p.write_text(f"# Plan {i}", encoding="utf-8")

        self.assertEqual(len(list(plans_dir.glob("TASK_PLAN_*.md"))), 12)

        # Prune with max_keep=5
        res = prune_scoped_plans(max_keep=5, workspace=self.test_dir)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["pruned_count"], 7)
        self.assertEqual(res["retained_count"], 5)
        self.assertEqual(len(list(plans_dir.glob("TASK_PLAN_*.md"))), 5)

    def test_sync_agents_cleans_stale_files(self):
        from squad_engine.agents_registry import sync_agents_to_workspace
        ws_agents = Path(self.test_dir) / ".agents" / "agents"
        ws_agents.mkdir(parents=True, exist_ok=True)

        # Create obsolete files
        stale_file = ws_agents / "qa-agent.md"
        stale_file.write_text("old content", encoding="utf-8")
        stale_file2 = ws_agents / "dev-agent.md"
        stale_file2.write_text("old content", encoding="utf-8")

        res = sync_agents_to_workspace(target_workspace=self.test_dir)
        self.assertEqual(res["status"], "SYNCHRONIZED")
        self.assertIn("qa-agent.md", res["removed_stale_files"])
        self.assertIn("dev-agent.md", res["removed_stale_files"])
        self.assertFalse(stale_file.exists())
        self.assertFalse(stale_file2.exists())
        # Active squad-*.md files must be present
        self.assertTrue((ws_agents / "squad-qa.md").exists())
        self.assertTrue((ws_agents / "squad-dev.md").exists())


if __name__ == "__main__":
    unittest.main()

