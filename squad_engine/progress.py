#!/usr/bin/env python3
"""
Project Progress Matrix & Acceptance Gate Tracker.
Parses, calculates statistics, and initializes PROJECT_PROGRESS.md.
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


def _write_with_lock(path: Path, content: str, encoding: str = "utf-8") -> None:
    """
    Write content to a file with advisory file locking to prevent concurrent corruption.
    Uses fcntl on Unix/macOS. Falls back to direct write on Windows.
    """
    try:
        import fcntl
        with open(path, "w", encoding=encoding) as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(content)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except ImportError:
        # Windows fallback — no fcntl, write directly
        path.write_text(content, encoding=encoding)


def parse_project_progress(progress_file_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Parses PROJECT_PROGRESS.md:
    - Calculates completion percentage
    - Counts done ([x]), in-progress ([-]), and pending ([ ]) items
    - Identifies modules awaiting QA sign-off or rejected
    - Extracts Next Recommended Action for Main Agent
    """
    candidates = []
    if progress_file_path:
        candidates.append(Path(progress_file_path))
    else:
        candidates.extend([
            Path.cwd() / "PROJECT_PROGRESS.md",
            Path.cwd() / ".agents" / "PROJECT_PROGRESS.md",
            Path.home() / ".gemini" / "antigravity" / "scratch" / "PROJECT_PROGRESS.md"
        ])

    target = None
    for c in candidates:
        if c.exists() and c.is_file():
            target = c
            break

    if not target or not target.exists():
        return {
            "status": "NOT_FOUND",
            "progress_percentage": 0.0,
            "total_tasks": 0,
            "completed_tasks": 0,
            "in_progress_tasks": 0,
            "pending_tasks": 0,
            "message": "PROJECT_PROGRESS.md not found. Use 'progress init' to create one."
        }

    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        return {"status": "ERROR", "message": f"Cannot read file: {e}"}

    lines = content.splitlines()

    done_items = []
    in_progress_items = []
    pending_items = []

    for line in lines:
        stripped = line.strip()
        if re.search(r"\[[xX]\]", stripped):
            done_items.append(stripped)
        elif re.search(r"\[[-/]\]", stripped):
            in_progress_items.append(stripped)
        elif re.search(r"\[\s\]", stripped):
            pending_items.append(stripped)

    total = len(done_items) + len(in_progress_items) + len(pending_items)
    if total > 0:
        percent = round((len(done_items) / total) * 100, 1)
    else:
        m = re.search(r"\*\*(\d+(?:\.\d+)?)\%\*\*", content)
        percent = float(m.group(1)) if m else 0.0

    ready_for_qa = [i for i in in_progress_items if re.search(r"READY_FOR_QA", i, re.IGNORECASE)]
    rejected_by_qa = [i for i in in_progress_items if re.search(r"REJECTED", i, re.IGNORECASE)]
    in_development = [i for i in in_progress_items if not re.search(r"READY_FOR_QA|REJECTED", i, re.IGNORECASE)]

    next_action = []
    capture = False
    for line in lines:
        if re.search(r"##\s*4\.\s*Đề xuất Bước Kế tiếp|##\s*Next Recommended Action", line, re.IGNORECASE):
            capture = True
            continue
        if capture:
            if line.startswith("## ") or line.startswith("---"):
                break
            if line.strip():
                next_action.append(line.strip())

    qa_summary_parts = []
    if ready_for_qa:
        qa_summary_parts.append(f"{len(ready_for_qa)} awaiting QA sign-off")
    if rejected_by_qa:
        qa_summary_parts.append(f"{len(rejected_by_qa)} rejected by QA (action required)")
    qa_extra = f" ({', '.join(qa_summary_parts)})" if qa_summary_parts else ""

    return {
        "status": "TRACKED",
        "file_path": str(target.resolve()),
        "progress_percentage": percent,
        "total_tasks": total,
        "completed_tasks": len(done_items),
        "in_progress_tasks": len(in_progress_items),
        "ready_for_qa_tasks": len(ready_for_qa),
        "rejected_by_qa_tasks": len(rejected_by_qa),
        "in_development_tasks": len(in_development),
        "pending_tasks": len(pending_items),
        "pending_tasks_list": pending_items,
        "next_recommended_action": "\n".join(next_action) if next_action else "No explicit next action declared.",
        "summary": f"{len(done_items)}/{total} tasks completed ({percent}%){qa_extra}"
    }


def init_project_progress(project_name: str, tasks: List[str], target_file: Optional[str] = None) -> Dict[str, Any]:
    """Initializes a standardized PROJECT_PROGRESS.md template for a new project."""
    target = Path(target_file) if target_file else Path.cwd() / "PROJECT_PROGRESS.md"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = []
    for idx, t in enumerate(tasks, start=1):
        status_tag = "[ ] PENDING"
        rows.append(f"| `{idx:02d}-{t.replace(' ', '-')}` | {t} | `{status_tag}` | Initial specification | Pending |")

    table_content = "\n".join(rows)
    first_task = tasks[0] if tasks else "Setup project foundation"

    template = f"""# Project Progress & Feature Completion Tracker: {project_name}

**Last Updated:** {now_str}
**Updated By:** `squad-dev`
**Overall Progress:** [--------------------] **0%** (0/{len(tasks)} modules completed)

---

## 1. Overview & Current Status
- **Current Milestone:** Phase 1 - Foundation & Architecture
- **Recently Completed:** Project initialized
- **System Stability:** Initializing

---

## 2. Feature Progress Matrix

| Module / Function | Scope / Description | Status | Notes from Squad Dev | Testing |
| :--- | :--- | :---: | :--- | :---: |
{table_content}

---

## 3. Files Created / Modified in this Session
- `[NEW]` `PROJECT_PROGRESS.md`

---

## 4. Next Recommended Action for Main Agent
1. **Next Task:** Execute first module: `{first_task}`.
2. **Target Files:** Define module structure in `src/`.
3. **Assigned Agent:** `squad-dev` (Model: inherit).
"""
    _write_with_lock(target, template)  # P3-C: concurrent-safe write


    return {
        "status": "INITIALIZED",
        "file_path": str(target.resolve()),
        "total_tasks": len(tasks),
        "progress_percentage": 0.0,
        "message": f"Created PROJECT_PROGRESS.md with {len(tasks)} tasks."
    }
