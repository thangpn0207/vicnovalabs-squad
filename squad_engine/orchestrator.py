#!/usr/bin/env python3
"""
Autonomous Squad Orchestrator Loop & Scoped Fan-Out Pipeline.
Tracks and transitions tasks in PROJECT_PROGRESS.md and handles closed-loop Defect/Handoff cycle.
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from .config import get_config
from .triage import dispatch_task, get_skills_for_phase, detect_platform
from .devices import audit_adb_devices, is_hardware_constrained, is_device_resume_prompt
from .handoffs import validate_handoff_payload
from .task_plan import (
    is_single_task,
    is_composite_or_large_task,
    decompose_large_task,
    init_scoped_task_plan,
    parse_scoped_task_plan,
    reconcile_scoped_task_plan,
    get_scoped_plans_dir
)


def is_handoff_manifest_prompt(text: str) -> bool:
    """Detects if user prompt represents an incoming Dev completion handoff."""
    if not text:
        return False
    t = text.lower()
    return bool(
        re.search(r"\b(handoffmanifest|handoff\s*manifest|self_test_result|verification_command|coverage_report)\b", t) or
        ("đã hoàn thành" in t and "handoff" in t) or
        ("ready_for_qa" in t and "test" in t)
    )


def requires_adversarial_review(text: str) -> bool:
    """Detects if request touches docs/specs, test strategy, architecture, or security requiring Adversarial Review."""
    if not text:
        return False
    t = text.lower()
    is_running_qa = bool(re.search(r"\b(chạy\s*(?:bộ\s*)?test|run\s*test|nghiệm\s*thu|qa[\s-]agent|playwright|e2e|smoke\s*test)\b", t))
    is_writing_strategy = bool(re.search(r"\b(lập\s*test\s*plan|kịch\s*bản\s*test|kịch\s*bản\s*kiểm\s*thử|chiến\s*lược\s*test|test\s*strategy)\b", t))
    if is_running_qa and not is_writing_strategy:
        return False

    from .semantic_evaluator import evaluate_task_semantics
    assessment = evaluate_task_semantics(text)
    return assessment.get("adversarial_risk") == "requires_skeptic_review"



def detect_adversarial_target(text: str) -> Dict[str, str]:
    """Detects target domain and assigns appropriate Skeptic Agent via Semantic Evaluator."""
    if not text:
        return {"target_domain": "architecture", "skeptic_agent": "debug-agent"}
    from .semantic_evaluator import evaluate_task_semantics
    assessment = evaluate_task_semantics(text)
    dom = assessment.get("adversarial_target_domain", "architecture")
    
    t = text.lower()
    test_pattern = r"\b(test\s*plan|kịch\s*bản\s*test|kịch\s*bản\s*kiểm\s*thử|chiến\s*lược\s*test|test\s*strategy|acceptance\s*criteria)\b"

    if dom == "auth_security":
        return {"target_domain": "security", "skeptic_agent": "debug-agent"}
    elif dom == "database_migration":
        return {"target_domain": "architecture", "skeptic_agent": "debug-agent"}
    elif dom == "docs_specification":
        if re.search(test_pattern, t):
            return {"target_domain": "test", "skeptic_agent": "dev-agent"}
        elif re.search(r"\b(testability|testable|khả\s*năng\s*kiểm\s*thử|acceptance|kiểm\s*thử|qa)\b", t):
            return {"target_domain": "docs", "skeptic_agent": "qa-agent"}
        return {"target_domain": "docs", "skeptic_agent": "debug-agent"}
    else:
        if re.search(test_pattern, t):
            return {"target_domain": "test", "skeptic_agent": "dev-agent"}
        return {"target_domain": "architecture", "skeptic_agent": "debug-agent"}



class SquadOrchestrator:
    """Coordinates lifecycle transitions between BA, Design, Dev, QA, and Debug agents."""

    def __init__(self, workspace_path: Optional[str] = None):
        self.config = get_config()
        self.workspace = Path(workspace_path).resolve() if workspace_path else self.config.repo_root
        self.progress_file = self.workspace / "PROJECT_PROGRESS.md"

    def read_progress(self) -> str:
        if self.progress_file.exists():
            return self.progress_file.read_text(encoding="utf-8")
        return ""

    def update_task_status(self, task_name: str, new_status: str, note: Optional[str] = None) -> bool:
        """Update checkbox and status tag for a task in PROJECT_PROGRESS.md."""
        if not self.progress_file.exists():
            return False
        
        content = self.progress_file.read_text(encoding="utf-8")
        status_map = {
            "TODO": "[ ] TODO",
            "IN_PROGRESS": "[/] IN_PROGRESS",
            "READY_FOR_QA": "[-] READY_FOR_QA",
            "REJECTED_BY_QA": "[-] REJECTED_BY_QA",
            "DONE": "[x] DONE",
            "BLOCKED": "[!] BLOCKED"
        }
        tag = status_map.get(new_status.upper(), new_status)
        
        pattern = re.compile(rf"(\s*-\s*\[[ x/\-!]\]\s*`?{re.escape(task_name)}`?:?\s*)(.*)", re.IGNORECASE)
        match = pattern.search(content)
        if match:
            old_line = match.group(0)
            note_str = f" — *{note}*" if note else ""
            new_line = f"  - {tag} `{task_name}`{note_str}"
            content = content.replace(old_line, new_line)
            self.progress_file.write_text(content, encoding="utf-8")
            return True
        return False

    def handle_handoff(self, manifest_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validate Dev handoff and transition task to READY_FOR_QA with coverage verification."""
        val = validate_handoff_payload("manifest", manifest_payload)
        if not val.get("valid"):
            return {
                "success": False,
                "action": "REJECT_HANDOFF",
                "errors": val.get("errors")
            }
        
        mod = manifest_payload.get("module", "Feature")
        cov = manifest_payload.get("coverage_report", {})
        cov_info = f"Diff Coverage: Line {cov.get('line_coverage_pct')}% / Branch {cov.get('branch_coverage_pct')}% ({cov.get('tool')})" if cov else "Self-test verified"
        self.update_task_status(mod, "READY_FOR_QA", note=f"Dev self-test & {cov_info} passed. Ready for QA acceptance.")
        
        return {
            "success": True,
            "action": "DISPATCH_QA",
            "module": mod,
            "verification_command": manifest_payload.get("verification_command"),
            "coverage_report": cov,
            "next_agent": "qa-agent"
        }

    def handle_defect(self, defect_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process QA DefectTicket and route back to dev-agent."""
        val = validate_handoff_payload("defect", defect_payload)
        if not val.get("valid"):
            return {"success": False, "errors": val.get("errors")}
        
        mod = defect_payload.get("module", "Feature")
        ticket_id = defect_payload.get("ticket_id", "DEF-001")
        self.update_task_status(mod, "REJECTED_BY_QA", note=f"QA Rejected with ticket {ticket_id}")
        
        return {
            "success": True,
            "action": "DISPATCH_DEV_BUGFIX",
            "ticket_id": ticket_id,
            "module": mod,
            "next_agent": "dev-agent"
        }

    def handle_signoff(self, receipt_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process QA SignoffReceipt with strict POAI validation and mark DONE."""
        val = validate_handoff_payload("acceptance", receipt_payload)
        if not val.get("valid"):
            return {
                "success": False,
                "action": "REJECT_SIGNOFF",
                "errors": val.get("errors")
            }
        
        mod = receipt_payload.get("module", "Feature")
        self.update_task_status(mod, "DONE", note="Accepted by QA SDET with POAI verification.")
        
        return {
            "success": True,
            "action": "MILESTONE_ACCEPTED",
            "module": mod,
            "status": "DONE"
        }


def orchestrate_pipeline(
    progress_file: Optional[str] = None,
    last_status: Optional[str] = None,
    defect_ticket: Optional[str] = None,
    user_prompt: Optional[str] = None,
    platform: str = "web",
    workspace: Optional[str] = None
) -> Dict[str, Any]:
    """Autonomous closed-loop orchestrator delegating prompt routing to Unified Squad Gate."""
    if user_prompt:
        from .gate import squad_gate
        return squad_gate(
            prompt=user_prompt,
            platform=platform,
            workspace=workspace
        )

    return {
        "decision": "IDLE",
        "next_role": None,
        "auto_chain": False,
        "message": "Orchestrator idle. No pending triggers."
    }
