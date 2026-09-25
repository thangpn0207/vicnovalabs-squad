#!/usr/bin/env python3
"""
Scoped Task Plan Engine & Hierarchical Multi-Agent Fan-Out.
Manages isolated TASK_PLAN_<slug>_<timestamp>.md plans in .agents/plans/
to prevent context pollution and multi-agent resource collisions.
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from .devices import audit_adb_devices, is_hardware_constrained, is_device_resume_prompt


SCOPED_PLANS_DIR_NAME = ".agents/plans"

COMPOSITE_TASK_PATTERN = re.compile(
    r"\b("
    r"toàn\s*bộ|tất\s*cả|toàn\s*app|toàn\s*bộ\s*hệ\s*thống|all\s*screens|toàn\s*bộ\s*màn\s*hình|"
    r"batch\s*test|test\s*hết|tổng\s*thể|refactor\s*đồng\s*thời|triển\s*khai\s*cùng\s*lúc|"
    r"test\s*đồng\s*thời|kiểm\s*thử\s*đồng\s*thời|song\s*song|parallel|fan[\s\-_]*out|map[\s\-_]*reduce|"
    r"chia\s*việc|nhiều\s*(?:dev|qa|agent|worker)|multi[\s\-_]*agent|multi[\s\-_]*worker|"
    r"đa\s*nền\s*tảng|multi[\s\-_]*platform|checklist|nghiệm\s*thu\s*toàn\s*diện"
    r")\b",
    re.IGNORECASE
)



def get_scoped_plans_dir(workspace: Optional[str] = None) -> Path:
    """Returns the dedicated directory for isolated task plans (.agents/plans/)."""
    base = Path(workspace) if workspace else Path.cwd()
    plans_dir = base / SCOPED_PLANS_DIR_NAME
    plans_dir.mkdir(parents=True, exist_ok=True)
    return plans_dir


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "_", cleaned)[:30]


def is_single_task(prompt: str, workspace: Optional[str] = None) -> bool:
    """Detects if prompt asks for an isolated single-step task exempt from pipeline chaining.
    Uses Tier A scope evaluation and composite exclusion instead of blocking common action verbs.
    """
    if not prompt:
        return False
    text = prompt.lower()

    # Option selections are handled by dedicated gate
    from .triage import OPTION_SELECTION_PATTERN
    if OPTION_SELECTION_PATTERN.search(text):
        return False

    # Explicit multi-agent / composite commands are definitely not single-tasks
    if COMPOSITE_TASK_PATTERN.search(text):
        return False

    single_indicators = [
        r"\b(chỉ|chỉ làm|chỉ cần|duy nhất|one-off|single task)\b",
        r"\b(giải thích|tại sao|nghĩa là gì|explain|what is|how does)\b",
        r"\b(sửa 1 lỗi|sửa typo|sửa 1 chữ|1 dòng|rename|comment|chỉnh 1 màu|sửa 1 nút)\b",
        r"\b(không cần test|không cần qa|bỏ qua test)\b"
    ]
    for pattern in single_indicators:
        if re.search(pattern, text):
            return True

    # Call Tier B (JEV Intent Classification)
    try:
        from .semantic_evaluator import classify_intent_tier_b
        tier_b = classify_intent_tier_b(prompt=prompt, workspace=workspace)
        if tier_b.get("is_single_task"):
            return True
    except Exception:
        pass

    # Check Tier A Scope Evaluator if explicit workspace diff exists
    if workspace:
        try:
            from .scope_evaluator import evaluate_scope_risk
            scope = evaluate_scope_risk(workspace_dir=workspace, prompt=prompt)
            if scope.modified_files:
                return scope.is_fast_path
        except Exception:
            pass

    return False


def is_composite_or_large_task(prompt: str) -> bool:
    """Detects if prompt asks for broad multi-module work via Single-Pass Semantic Evaluator."""
    if not prompt:
        return False
    if is_single_task(prompt):
        return False
    from .triage import OPTION_SELECTION_PATTERN
    if OPTION_SELECTION_PATTERN.search(prompt):
        return False
    from .semantic_evaluator import evaluate_task_semantics
    assessment = evaluate_task_semantics(prompt)
    topology = assessment.get("execution_topology")
    if topology == "scoped_fanout":
        # Guard: Fan-out should only happen if there is an explicit fan-out indicator,
        # multi-platform testing, or an actual multi-item checklist in the prompt.
        # Do not fan-out for a single domain feature request (e.g. testing photo upload/download).
        text = prompt.lower()
        has_explicit_fanout = bool(re.search(
            r"\b(chia\s*việc|song\s*song|nhiều\s*dev|nhiều\s*qa|multi\s*agent|fan[\s-]out|map[\s-]reduce|"
            r"toàn\s*bộ|tất\s*cả|toàn\s*app|batch\s*test|parallel)\b",
            text
        ))
        has_multiplatform = (bool(re.search(r"\b(android|apk)\b", text)) and bool(re.search(r"\b(ios|iphone|simulator)\b", text)))
        has_checklist = len([l for l in prompt.splitlines() if re.match(r"^\s*(?:[-*•]|\d+[.)])\s+", l.strip())]) >= 3
        return bool(has_explicit_fanout or has_multiplatform or has_checklist)
    return False




def decompose_large_task(prompt: str, platform: str = "mobile", workspace: Optional[str] = None) -> Dict[str, Any]:
    """Decomposes a broad prompt into distinct subtasks with assigned roles and resource partitions."""
    text = prompt.lower()
    from .triage import triage_intent
    triage_res = triage_intent(prompt)
    role = triage_res.get("role", "dev")
    if role not in ["dev", "qa"]:
        role = "dev"
    target_agent = f"squad-{role}"

    matched_modules = []
    partition_strategy = "DISJOINT_MODULE_PARTITION"

    # 1. First priority: Check if prompt contains an explicit multi-item checklist (>= 2 items)
    prompt_checklist = []
    for line in prompt.splitlines():
        line_clean = line.strip()
        m_bullet = re.match(r"^(?:[-*•]|\d+[.)])\s+(?:\[[ x\-/]\]\s*)?([^\n*—|:]+)(?::\s*([^\n*—|]+))?", line_clean)
        if m_bullet:
            item_title = m_bullet.group(1).strip()
            item_desc = (m_bullet.group(2) or "").strip()
            # Ignore headers, section markers, or generic instructions
            if item_title and not any(k in item_title.lower() for k in ["checklist", "tiêu chí", "mục tiêu", "lưu ý", "khởi động", "build & cài", "thao tác nghiệm thu"]):
                full_item = f"{item_title}: {item_desc}" if item_desc else item_title
                prompt_checklist.append((item_title, full_item))

    if len(prompt_checklist) >= 2:
        for item_title, full_item in prompt_checklist[:6]:
            path_hint = f"features/{slugify(item_title)[:15]}/"
            matched_modules.append((full_item, path_hint))
        partition_strategy = "PROMPT_CHECKLIST_PARTITION"

    # 2. Second priority: Multi-platform QA partition (Android + iOS)
    if not matched_modules and role == "qa":
        has_android = bool(re.search(r"\b(android|apk|emulator)\b", text))
        has_ios = bool(re.search(r"\b(ios|iphone|simulator)\b", text))
        if has_android and has_ios:
            matched_modules = [
                ("Android Acceptance Journey (Android Emulator)", "platform/android/"),
                ("iOS Acceptance Journey (iOS Simulator)", "platform/ios/")
            ]
            partition_strategy = "MULTI_PLATFORM_PARTITION"

    # 3. Third priority: Dynamic Backlog Extraction from PROJECT_PROGRESS.md
    if not matched_modules:
        extracted_backlog = []
        base_dir = Path(workspace) if workspace else Path.cwd()
        prog_candidates = [
            base_dir / "PROJECT_PROGRESS.md",
            Path.cwd() / "PROJECT_PROGRESS.md",
            Path(__file__).resolve().parent.parent / "PROJECT_PROGRESS.md"
        ]
        prog_path = None
        for cand in prog_candidates:
            if cand.exists() and cand.is_file():
                prog_path = cand
                break

        if prog_path and prog_path.exists():
            try:
                content = prog_path.read_text(encoding="utf-8")
                for line in content.splitlines():
                    line_s = line.strip()
                    # Match standard markdown checkbox pending/in-progress items:
                    m_item = re.search(r"^-\s*\[([ \-/])\]\s*(?:(?:`([^`]+)`|([^\n*—|:]+))(?::\s*([^\n*—|]+))?)", line_s)
                    if m_item:
                        name_part = (m_item.group(2) or m_item.group(3) or "").strip()
                        desc_part = (m_item.group(4) or "").strip()
                        cleaned_name = re.sub(r"^(?:TODO|PENDING|IN_PROGRESS|READY_FOR_QA)\s*`?", "", name_part).strip("` :")
                        if cleaned_name and not cleaned_name.lower().startswith("checklist"):
                            full_title = f"{cleaned_name}: {desc_part}" if desc_part else cleaned_name
                            extracted_backlog.append((cleaned_name, full_title))
                    # Match table rows: | `01-auth` | Authentication | `[ ] PENDING` | ...
                    elif line_s.startswith("|") and re.search(r"\[[ \-/]\]", line_s):
                        cols = [c.strip() for c in line_s.split("|")[1:-1]]
                        if len(cols) >= 3:
                            mod_col = cols[0].replace("`", "").strip()
                            title_col = cols[1].strip()
                            if title_col and title_col != "Scope / Description":
                                extracted_backlog.append((mod_col, f"{mod_col} ({title_col})"))
            except Exception:
                pass

        if extracted_backlog:
            for mod_id, full_title in extracted_backlog[:5]:
                path_hint = f"src/{slugify(mod_id)[:15]}/" if not ("/" in mod_id or "." in mod_id) else mod_id
                matched_modules.append((full_title, path_hint))
            partition_strategy = "DYNAMIC_BACKLOG_PARTITION"

    # 4. Fourth priority: Known modules vocabulary
    if not matched_modules:
        known_modules = [
            ("Pairing & QR Exchange", r"\b(pair|pairing|qr|kết\s*nối|ghép\s*đôi)\b", "pairing/"),
            ("Space Chat & Messaging", r"\b(chat|tin\s*nhắn|messages?|spaces?|timeline)\b", "chat/"),
            ("Payment & Checkout Engine", r"\b(pay|payment|thanh\s*toán|billing|checkout|cart|giỏ\s*hàng)\b", "payment/"),
            ("Settings & Storage Diagnostics", r"\b(settings?|cài\s*đặt|storage|lưu\s*trữ|cấu\s*hình)\b", "settings/"),
            ("Authentication & Identity", r"\b(auth|xác\s*thực|identity|đăng\s*nhập|login)\b", "auth/"),
            ("Daily Ritual & Interactions", r"\b(rituals?|nghi\s*thức|interactions?|thẻ|cards?)\b", "ritual/"),
            ("Notifications & Messaging", r"\b(notif|notification|thông\s*báo)\b", "notifications/"),
            ("Core Services & APIs", r"\b(api|endpoint|database|db|models?|services?)\b", "services/")
        ]
        for m_title, m_pat, m_path in known_modules:
            if re.search(m_pat, text):
                matched_modules.append((m_title, m_path))

    # 5. Default fallback partitions
    if not matched_modules:
        if platform == "mobile":
            matched_modules = [
                ("Pairing & Core Handshake", "lib/engine/pairing/"),
                ("Spaces & Interactive UI", "lib/features/spaces/"),
                ("Settings & Data Hygiene", "lib/features/settings/")
            ]
        else:
            matched_modules = [
                ("Module Alpha (Core Foundation)", "src/core/"),
                ("Module Beta (Interactive Journey)", "src/features/"),
                ("Module Gamma (State & Hygiene)", "src/services/")
            ]
    elif len(matched_modules) == 1:
        single_title, single_path = matched_modules[0]
        matched_modules = [
            (f"{single_title} (Core Logic)", f"{single_path}core/"),
            (f"{single_title} (Service & Integration)", f"{single_path}services/")
        ]

    audit = audit_adb_devices()
    can_dual = audit.get("can_run_dual_device", False)
    phys_serial = audit["physical_devices"][0]["serial"] if audit.get("has_physical_device") and audit["physical_devices"] else None
    emul_serial = audit["emulators"][0]["serial"] if audit.get("emulators") else "emulator-5554"

    subtasks = []
    for i, (m_title, m_path) in enumerate(matched_modules, start=1):
        sub_id = f"ST-{i:02d}"
        if role == "qa":
            if "android" in m_title.lower():
                partition = f"Android Emulator Environment (`{emul_serial}`)"
            elif "ios" in m_title.lower():
                partition = "iOS Simulator Environment (`booted`)"
            elif can_dual and i == 1:
                partition = f"Dual-Device Handshake (`{emul_serial}` & `{phys_serial}`)"
            elif can_dual and i == 2:
                partition = f"Emulator Journey (`{emul_serial}`)"
            elif can_dual and i == 3:
                partition = f"Physical Journey (`{phys_serial}`)"
            else:
                partition = f"Target Journey (`{m_path}`) on Device (`{emul_serial}`)"
        else:
            partition = f"Disjoint File Tree (`{m_path}`)"

        subtasks.append({
            "id": sub_id,
            "title": m_title,
            "partition": partition,
            "role": role,
            "target_agent": target_agent,
            "status": "[ ] PENDING",
            "notes": "Pending execution partition"
        })

    return {
        "title": prompt[:60].strip(),
        "role": role,
        "platform": platform,
        "total_subtasks": len(subtasks),
        "partition_strategy": partition_strategy,
        "subtasks": subtasks
    }



def init_scoped_task_plan(
    title: str,
    subtasks: List[Any],
    partition_strategy: str = "AUTO",
    workspace: Optional[str] = None
) -> Dict[str, Any]:
    """Creates an isolated TASK_PLAN_<timestamp>.md in .agents/plans/."""
    plans_dir = get_scoped_plans_dir(workspace)
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    timestamp_id = now.strftime("%Y%m%d_%H%M%S")
    slug = slugify(title)
    file_name = f"TASK_PLAN_{slug}_{timestamp_id}.md"
    plan_path = plans_dir / file_name

    norm_subtasks = []
    for idx, item in enumerate(subtasks, start=1):
        if isinstance(item, dict):
            s_id = item.get("id", f"ST-{idx:02d}")
            s_title = item.get("title", f"Subtask {idx}")
            s_part = item.get("partition", f"Partition-{idx}")
            s_agent = item.get("target_agent", "squad-qa")
            s_status = item.get("status", "[ ] PENDING")
            s_notes = item.get("notes", "Initialized")
        else:
            s_id = f"ST-{idx:02d}"
            s_title = str(item)
            s_part = f"Partition-{idx}"
            s_agent = "squad-qa"
            s_status = "[ ] PENDING"
            s_notes = "Initialized"
        norm_subtasks.append({
            "id": s_id,
            "title": s_title,
            "partition": s_part,
            "target_agent": s_agent,
            "status": s_status,
            "notes": s_notes
        })

    rows = []
    for st in norm_subtasks:
        rows.append(f"| `{st['id']}` | {st['title']} | {st['partition']} | `{st['target_agent']}` | `{st['status']}` | {st['notes']} |")

    table_md = "\n".join(rows)

    content = f"""# Scoped Task Plan: {title}

**Plan ID:** `TASK-{timestamp_id}`
**Created At:** {now_str}
**Status:** `IN_PROGRESS`
**Overall Progress:** 0% (0/{len(norm_subtasks)} subtasks completed)
**Partition Strategy:** `{partition_strategy}`
**Target Directory:** `{plans_dir}`

---

## 1. Subtask Decomposition Matrix

| Subtask ID | Subtask Title | Resource Partition | Assigned Agent | Status | Notes & Results |
|---|---|---|---|---|---|
{table_md}

---

## 2. Partitioning & Isolation Discipline Constraints
1. **Isolated Resource Partitioning**: Subagents may only operate on and modify files within their assigned Resource Partition.
2. **Zero Root Progress Contamination**: Subagents MUST NOT edit `PROJECT_PROGRESS.md` directly. Update subtask status on this plan via:
   ```bash
   squad task-plan update --plan {plan_path} --subtask <id> --status <status> --note "<result>"
   ```
3. **Barrier Synchronization**: Only after all subtasks in this matrix reach `[x] DONE` does the Orchestrator reconcile and update the root `PROJECT_PROGRESS.md`.
"""
    plan_path.write_text(content, encoding="utf-8")

    # Auto-prune older plans to prevent cache bloat (retain 15 most recent)
    try:
        prune_scoped_plans(max_keep=15, workspace=workspace)
    except Exception:
        pass

    return {
        "status": "success",
        "plan_id": f"TASK-{timestamp_id}",
        "file_name": file_name,
        "file_path": str(plan_path),
        "total_subtasks": len(norm_subtasks),
        "partition_strategy": partition_strategy,
        "subtasks": norm_subtasks
    }


def parse_scoped_task_plan(plan_file: Optional[str] = None, workspace: Optional[str] = None) -> Dict[str, Any]:
    """Parses a scoped task plan markdown file, extracting progress and subtask states."""
    if not plan_file:
        plans_dir = get_scoped_plans_dir(workspace)
        all_plans = sorted(plans_dir.glob("TASK_PLAN_*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not all_plans:
            return {"status": "not_found", "message": "No scoped task plans found in .agents/plans/."}
        p_path = all_plans[0]
    else:
        p_path = Path(plan_file)
        if not p_path.exists():
            return {"status": "error", "message": f"Plan file not found: {plan_file}"}

    text = p_path.read_text(encoding="utf-8")
    title_match = re.search(r"#\s*Scoped Task Plan:\s*(.*)", text)
    title = title_match.group(1).strip() if title_match else p_path.stem

    plan_id_match = re.search(r"\*\*Plan ID:\*\*\s*`([^`]+)`", text)
    plan_id = plan_id_match.group(1).strip() if plan_id_match else "UNKNOWN"

    status_match = re.search(r"\*\*Status:\*\*\s*`([^`]+)`", text)
    overall_status = status_match.group(1).strip() if status_match else "UNKNOWN"

    subtasks = []
    lines = text.splitlines()
    table_started = False
    for line in lines:
        line_s = line.strip()
        if line_s.startswith("| Subtask ID"):
            table_started = True
            continue
        if table_started:
            if line_s.startswith("|---") or line_s.startswith("|:--"):
                continue
            if not line_s.startswith("|"):
                if line_s.startswith("## ") or not line_s:
                    table_started = False
                continue
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 5:
                s_id = cols[0].replace("`", "")
                s_title = cols[1]
                s_partition = cols[2]
                s_agent = cols[3].replace("`", "")
                s_status = cols[4].replace("`", "")
                s_notes = cols[5] if len(cols) >= 6 else ""
                subtasks.append({
                    "id": s_id,
                    "title": s_title,
                    "partition": s_partition,
                    "target_agent": s_agent,
                    "status": s_status,
                    "notes": s_notes,
                    "is_done": "[x]" in s_status or "DONE" in s_status.upper()
                })

    done_count = sum(1 for s in subtasks if s["is_done"])
    total_count = len(subtasks)
    pct = round((done_count / total_count * 100)) if total_count > 0 else 0

    return {
        "status": "success",
        "plan_id": plan_id,
        "title": title,
        "file_name": p_path.name,
        "file_path": str(p_path),
        "overall_status": overall_status,
        "completed_count": done_count,
        "total_subtasks": total_count,
        "progress_percent": pct,
        "is_completed": done_count == total_count and total_count > 0,
        "subtasks": subtasks
    }


def update_scoped_task_plan(
    plan_file: str,
    subtask_id: str,
    status: str,
    note: Optional[str] = None,
    workspace: Optional[str] = None
) -> Dict[str, Any]:
    """Updates the status and notes of a specific subtask within a scoped plan."""
    p_path = Path(plan_file)
    if not p_path.exists():
        plans_dir = get_scoped_plans_dir(workspace)
        cand = plans_dir / plan_file
        if cand.exists():
            p_path = cand
        else:
            return {"status": "error", "message": f"Plan file not found: {plan_file}"}

    text = p_path.read_text(encoding="utf-8")
    status_clean = status.upper().strip()
    if not status_clean.startswith("["):
        if status_clean in ["DONE", "PASSED", "PASS"]:
            formatted_status = "[x] DONE"
        elif status_clean in ["READY_FOR_QA", "QA"]:
            formatted_status = "[-] READY_FOR_QA"
        elif status_clean in ["IN_PROGRESS", "RUNNING"]:
            formatted_status = "[/] IN_PROGRESS"
        elif status_clean in ["BLOCKED", "FAIL", "REJECTED"]:
            formatted_status = "[!] BLOCKED"
        else:
            formatted_status = f"[{status_clean}]"
    else:
        formatted_status = status_clean

    lines = text.splitlines()
    found = False
    new_lines = []

    for line in lines:
        line_s = line.strip()
        if line_s.startswith("|") and f"`{subtask_id}`" in line:
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 5:
                cols[4] = f"`{formatted_status}`"
                if note:
                    cols[5] = note.strip()
                rebuilt_row = "| " + " | ".join(cols) + " |"
                new_lines.append(rebuilt_row)
                found = True
                continue
        new_lines.append(line)

    if not found:
        return {"status": "error", "message": f"Subtask ID '{subtask_id}' not found in {p_path.name}"}

    new_text = "\n".join(new_lines)
    p_path.write_text(new_text, encoding="utf-8")

    parsed = parse_scoped_task_plan(str(p_path))
    new_text = re.sub(
        r"\*\*Overall Progress:\*\*\s*[0-9]+%.*",
        f"**Overall Progress:** {parsed['progress_percent']}% ({parsed['completed_count']}/{parsed['total_subtasks']} subtasks completed)",
        new_text
    )
    if parsed["is_completed"]:
        new_text = re.sub(r"\*\*Status:\*\*\s*`[^`]+`", "**Status:** `COMPLETED`", new_text)

    p_path.write_text(new_text, encoding="utf-8")

    return {
        "status": "success",
        "plan_file": str(p_path),
        "subtask_id": subtask_id,
        "new_status": formatted_status,
        "note": note,
        "progress_percent": parsed["progress_percent"],
        "is_all_completed": parsed["is_completed"]
    }


def reconcile_scoped_task_plan(
    plan_file: Optional[str] = None,
    progress_file: Optional[str] = None,
    workspace: Optional[str] = None
) -> Dict[str, Any]:
    """Reconciles completed scoped subtasks into root PROJECT_PROGRESS.md (Barrier Sync)."""
    parsed = parse_scoped_task_plan(plan_file, workspace=workspace)
    if parsed.get("status") != "success":
        return parsed

    base = Path(workspace) if workspace else Path.cwd()
    prog_path = Path(progress_file) if progress_file else base / "PROJECT_PROGRESS.md"

    if not prog_path.exists():
        return {
            "status": "warning",
            "message": f"Root progress file {prog_path.name} not found. Barrier sync recorded in plan only.",
            "plan_progress": parsed
        }

    content = prog_path.read_text(encoding="utf-8")
    synced_items = []

    for st in parsed["subtasks"]:
        if st["is_done"]:
            title_pat = re.escape(st["title"])
            pattern = re.compile(rf"-\s*\[[ \-/!]\]\s*(`?{title_pat}`?.*)", re.IGNORECASE)
            if pattern.search(content):
                content = pattern.sub(rf"- [x] \1 *(Reconciled from `{parsed['file_name']}`)*", content)
                synced_items.append(st["id"])

    prog_path.write_text(content, encoding="utf-8")

    return {
        "status": "success",
        "plan_id": parsed["plan_id"],
        "reconciled_subtasks": synced_items,
        "all_subtasks_done": parsed["is_completed"],
        "progress_file": str(prog_path)
    }


def prune_scoped_plans(max_keep: int = 10, workspace: Optional[str] = None) -> Dict[str, Any]:
    """Prunes obsolete scoped task plans, keeping only the most recent `max_keep` files."""
    plans_dir = get_scoped_plans_dir(workspace)
    plans = sorted(plans_dir.glob("TASK_PLAN_*.md"), key=lambda f: f.stat().st_mtime, reverse=True)

    if len(plans) <= max_keep:
        return {
            "status": "success",
            "total_plans": len(plans),
            "pruned_count": 0,
            "pruned_files": [],
            "retained_count": len(plans)
        }

    to_delete = plans[max_keep:]
    pruned_files = []
    for p in to_delete:
        try:
            name = p.name
            p.unlink()
            pruned_files.append(name)
        except Exception:
            pass

    return {
        "status": "success",
        "total_plans": len(plans),
        "pruned_count": len(pruned_files),
        "pruned_files": pruned_files,
        "retained_count": len(plans) - len(pruned_files)
    }

