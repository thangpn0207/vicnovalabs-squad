#!/usr/bin/env python3
"""
Superpowers-Inspired Git Worktrees Isolation for Parallel Squad Subagents.
Allows concurrent squad-dev subagents to develop independent modules in isolated worktrees
without file conflicts, race conditions, or git lock collisions.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional


def _run_git_cmd(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False
    )


def create_task_worktree(
    repo_root: str,
    task_slug: str,
    base_commit: str = "HEAD"
) -> Dict[str, Any]:
    """
    Create an isolated git worktree for a parallel subagent under .worktrees/<task_slug>.
    """
    root = Path(repo_root).resolve()
    slug_clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", task_slug).strip("_")
    worktree_dir = root / ".worktrees" / slug_clean
    branch_name = f"squad/{slug_clean}"

    if worktree_dir.exists():
        return {
            "success": True,
            "status": "already_exists",
            "worktree_path": str(worktree_dir),
            "branch": branch_name
        }

    # 1. Check if git repository
    chk = _run_git_cmd(["git", "rev-parse", "--is-inside-work-tree"], root)
    if chk.returncode != 0:
        return {
            "success": False,
            "error": "Not a valid git repository. Git worktrees require an active git root."
        }

    # 2. Add git worktree
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)
    res = _run_git_cmd(["git", "worktree", "add", "-b", branch_name, str(worktree_dir), base_commit], root)

    # Fallback if branch already exists: checkout without -b
    if res.returncode != 0 and "already exists" in res.stderr:
        res = _run_git_cmd(["git", "worktree", "add", str(worktree_dir), branch_name], root)

    if res.returncode != 0:
        return {
            "success": False,
            "error": f"Failed to create git worktree: {res.stderr.strip()}"
        }

    return {
        "success": True,
        "status": "created",
        "worktree_path": str(worktree_dir),
        "branch": branch_name
    }


def list_task_worktrees(repo_root: str) -> List[Dict[str, Any]]:
    """List all active git worktrees in the repository."""
    root = Path(repo_root).resolve()
    res = _run_git_cmd(["git", "worktree", "list", "--porcelain"], root)
    if res.returncode != 0:
        return []

    worktrees = []
    current_entry = {}
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line:
            if current_entry:
                worktrees.append(current_entry)
                current_entry = {}
            continue
        if line.startswith("worktree "):
            current_entry["worktree"] = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            current_entry["branch"] = line.split(" ", 1)[1]
        elif line.startswith("HEAD "):
            current_entry["head"] = line.split(" ", 1)[1]

    if current_entry:
        worktrees.append(current_entry)

    # Filter to only squad worktrees
    squad_trees = [w for w in worktrees if ".worktrees" in w.get("worktree", "") or "squad/" in w.get("branch", "")]
    return squad_trees


def remove_task_worktree(repo_root: str, task_slug: str, force: bool = False) -> Dict[str, Any]:
    """Remove a finished or cancelled git worktree."""
    root = Path(repo_root).resolve()
    slug_clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", task_slug).strip("_")
    worktree_dir = root / ".worktrees" / slug_clean

    cmd = ["git", "worktree", "remove", str(worktree_dir)]
    if force:
        cmd.append("--force")

    res = _run_git_cmd(cmd, root)
    if res.returncode != 0:
        return {"success": False, "error": res.stderr.strip()}

    return {"success": True, "removed": str(worktree_dir)}


def merge_task_worktree(
    repo_root: str,
    task_slug: str,
    test_command: Optional[str] = None
) -> Dict[str, Any]:
    """
    Merge the subagent's worktree branch back into the current branch safely.

    Phase 6.2 Safe Merge Protocol:
    1. Checks if the main repository working tree is dirty (rejects if dirty).
    2. Runs test_command in the worktree directory if specified (test-before-merge).
    3. Merges branch. If conflicts arise, aborts merge cleanly to prevent corrupted state.
    4. Cleans up the worktree directory on success.
    """
    root = Path(repo_root).resolve()
    slug_clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", task_slug).strip("_")
    worktree_dir = root / ".worktrees" / slug_clean
    branch_name = f"squad/{slug_clean}"

    # 1. Dirty working tree protection (excluding .worktrees runtime artifacts)
    status_res = _run_git_cmd(["git", "status", "--porcelain"], root)
    if status_res.returncode == 0:
        dirty_lines = [
            l for l in status_res.stdout.splitlines()
            if l.strip() and ".worktrees" not in l
        ]
        if dirty_lines:
            return {
                "success": False,
                "error": "Dirty working tree in target repo. Commit, stash, or clean working tree before merging task worktree."
            }


    # 2. Test-before-merge verification
    if test_command:
        if not worktree_dir.exists():
            return {
                "success": False,
                "error": f"Worktree directory not found at {worktree_dir} for test-before-merge."
            }
        test_run = subprocess.run(
            test_command,
            shell=True,
            cwd=str(worktree_dir),
            capture_output=True,
            text=True
        )
        if test_run.returncode != 0:
            return {
                "success": False,
                "error": f"Test-before-merge failed with exit code {test_run.returncode}: {test_run.stderr.strip() or test_run.stdout.strip()}"
            }

    # 3. Merge with conflict protection
    res = _run_git_cmd(["git", "merge", "--no-ff", "-m", f"Merge parallel squad subagent: {slug_clean}", branch_name], root)
    if res.returncode != 0:
        # Abort the conflicted merge cleanly
        _run_git_cmd(["git", "merge", "--abort"], root)
        return {
            "success": False,
            "conflict": True,
            "error": f"Merge conflict detected when merging {branch_name}. Aborted merge cleanly: {res.stderr.strip()}"
        }

    # 4. Automatically clean up worktree after successful merge
    remove_task_worktree(repo_root, slug_clean, force=True)

    return {
        "success": True,
        "merged_branch": branch_name
    }

