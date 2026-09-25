#!/usr/bin/env python3
"""
Tests for 3-Tier Memory, Context Compactor, and Git Worktrees Isolation.
"""

import tempfile
import unittest
import subprocess
from pathlib import Path
from squad_engine.memory import SquadMemory, compact_context_text
from squad_engine.worktrees import create_task_worktree, list_task_worktrees, remove_task_worktree, merge_task_worktree


class TestMemoryAndWorktrees(unittest.TestCase):

    def test_squad_memory_three_tier_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mem = SquadMemory(workspace_path=tmpdir)
            self.assertTrue(mem.soul_file.exists())
            self.assertTrue(mem.memory_file.exists())
            self.assertTrue(mem.working_file.exists())

            # Read initial
            self.assertIn("Proof-of-Active-Interaction", mem.read_soul())

            # Append long-term insight
            mem.append_long_term_insight("Supabase RLS", "Always specify auth.uid() check on tenant_id.")
            self.assertIn("Supabase RLS", mem.read_memory())
            self.assertIn("tenant_id", mem.read_memory())

            # Update working scratchpad
            mem.update_working_scratchpad("Stripe Checkout", "IN_PROGRESS", "Testing webhook replay")
            self.assertIn("Stripe Checkout", mem.read_working())
            self.assertIn("Testing webhook replay", mem.read_working())

            bundle = mem.get_summary_bundle()
            self.assertEqual(bundle["status"], "active")
            self.assertGreater(bundle["total_tokens"], 10)

    def test_context_compactor(self):
        # 1. Short text passes through intact
        short = "Line 1\nLine 2\nLine 3"
        self.assertEqual(compact_context_text(short), short)

        # 2. Large noisy text gets compacted
        noisy_lines = ["Starting build..."]
        for i in range(100):
            noisy_lines.append(f"Progress bar {i}% [=====>        ]")
            noisy_lines.append(f"Compiling widget_{i}.dart with warnings...")
        noisy_lines.append("Build Finished Successfully with 0 errors.")

        giant_text = "\n".join(noisy_lines)
        compacted = compact_context_text(giant_text, max_lines=20)
        self.assertIn("Context Compactor: Omitted", compacted)
        self.assertIn("Starting build...", compacted)
        self.assertIn("Build Finished Successfully", compacted)
        self.assertLess(len(compacted.splitlines()), 30)

    def test_git_worktrees_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Initialize a real git repo in temp dir
            subprocess.run(["git", "init"], cwd=tmpdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=tmpdir, check=True)
            subprocess.run(["git", "config", "user.email", "test@vicnovalabs.com"], cwd=tmpdir, check=True)

            dummy_file = tmppath / "README.md"
            dummy_file.write_text("# Initial Repo", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=tmpdir, check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmpdir, check=True)

            # 1. Create worktree
            res = create_task_worktree(tmpdir, "feat-payment")
            self.assertTrue(res["success"])
            self.assertTrue(Path(res["worktree_path"]).exists())

            # 2. List worktrees
            trees = list_task_worktrees(tmpdir)
            self.assertEqual(len(trees), 1)
            self.assertIn("feat-payment", trees[0]["worktree"])

            # 3. Commit inside worktree
            wt_file = Path(res["worktree_path"]) / "payment.py"
            wt_file.write_text("def pay(): pass", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=res["worktree_path"], check=True)
            subprocess.run(["git", "commit", "-m", "Add payment module"], cwd=res["worktree_path"], check=True)

            # 4. Merge worktree back to main
            merge_res = merge_task_worktree(tmpdir, "feat-payment")
            self.assertTrue(merge_res["success"])
            self.assertTrue((tmppath / "payment.py").exists())
            self.assertFalse(Path(res["worktree_path"]).exists())


if __name__ == "__main__":
    unittest.main()
