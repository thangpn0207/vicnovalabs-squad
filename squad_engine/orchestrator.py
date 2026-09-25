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
from .evidence_oracle import validate_evidence_bundle
from .stack_detector import detect_project_stack
from .task_plan import (
    is_single_task,
    is_composite_or_large_task,
    decompose_large_task,
    init_scoped_task_plan,
    parse_scoped_task_plan,
    reconcile_scoped_task_plan,
    get_scoped_plans_dir
)


BANNED_PHRASES = [
    "great question", "excellent request", "hope this helps",
    "let me know if you need anything else", "don't hesitate to ask",
    "HandoffManifest", "SignoffReceipt", "Torture Dimension", "POAI",
    "Squad Dispatch Card"
]


def sanitize_response(text: str) -> str:
    """Post-processing linter: strips banned flatteries and internal machinery names."""
    if not text:
        return ""
    lines = []
    for line in text.splitlines():
        cleaned_line = line
        for phrase in BANNED_PHRASES:
            if phrase.lower() in cleaned_line.lower():
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                cleaned_line = pattern.sub("", cleaned_line).strip()
        if cleaned_line:
            lines.append(cleaned_line)
    return "\n".join(lines)


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
        return {"target_domain": "architecture", "skeptic_agent": "squad-debug"}
    from .semantic_evaluator import evaluate_task_semantics
    assessment = evaluate_task_semantics(text)
    dom = assessment.get("adversarial_target_domain", "architecture")
    
    t = text.lower()
    test_pattern = r"\b(test\s*plan|kịch\s*bản\s*test|kịch\s*bản\s*kiểm\s*thử|chiến\s*lược\s*test|test\s*strategy|acceptance\s*criteria)\b"

    if dom == "auth_security":
        return {"target_domain": "security", "skeptic_agent": "squad-debug"}
    elif dom == "database_migration":
        return {"target_domain": "architecture", "skeptic_agent": "squad-debug"}
    elif dom == "docs_specification":
        if re.search(test_pattern, t):
            return {"target_domain": "test", "skeptic_agent": "squad-dev"}
        elif re.search(r"\b(testability|testable|khả\s*năng\s*kiểm\s*thử|acceptance|kiểm\s*thử|qa)\b", t):
            return {"target_domain": "docs", "skeptic_agent": "squad-qa"}
        return {"target_domain": "docs", "skeptic_agent": "squad-debug"}
    else:
        if re.search(test_pattern, t):
            return {"target_domain": "test", "skeptic_agent": "squad-dev"}
        return {"target_domain": "architecture", "skeptic_agent": "squad-debug"}



MAX_DEFECT_LOOPBACKS = 2


class SquadOrchestrator:
    """Coordinates lifecycle transitions between BA, Design, Dev, QA, and Debug agents."""

    def __init__(self, workspace_path: Optional[str] = None):
        self.config = get_config()
        self.workspace = Path(workspace_path).resolve() if workspace_path else self.config.repo_root
        self.progress_file = self.workspace / "PROJECT_PROGRESS.md"
        self.defect_counts: Dict[str, int] = self._load_defect_counts()

    def _load_defect_counts(self) -> Dict[str, int]:
        """Load persistent defect counters from PROJECT_PROGRESS.md metadata comment."""
        if not self.progress_file.exists():
            return {}
        try:
            content = self.progress_file.read_text(encoding="utf-8")
            match = re.search(r"<!--\s*defect_counts:\s*(\{[^}]*\})\s*-->", content)
            if match:
                return json.loads(match.group(1))
        except Exception:
            pass
        return {}

    def _persist_defect_counts(self) -> None:
        """Write defect counters as a metadata comment in PROJECT_PROGRESS.md."""
        if not self.progress_file.exists():
            return
        try:
            content = self.progress_file.read_text(encoding="utf-8")
            tag = f"<!-- defect_counts: {json.dumps(self.defect_counts)} -->"
            # Replace existing tag or append at end
            if re.search(r"<!--\s*defect_counts:", content):
                content = re.sub(r"<!--\s*defect_counts:[^>]*-->", tag, content)
            else:
                content = content.rstrip() + f"\n\n{tag}\n"
            self.progress_file.write_text(content, encoding="utf-8")
        except Exception:
            pass

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
        
        pattern = re.compile(rf"(\s*-\s*\[[ x/\-!]\](?:\s+[A-Z_]+)?\s*`?{re.escape(task_name)}`?:?\s*)(.*)", re.IGNORECASE)
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
            "next_agent": "squad-qa"
        }

    def handle_defect(self, defect_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process QA DefectTicket and route back to squad-dev with ping-pong circuit breaker."""
        val = validate_handoff_payload("defect", defect_payload)
        if not val.get("valid"):
            return {"success": False, "errors": val.get("errors")}
        
        mod = defect_payload.get("module", "Feature")
        ticket_id = defect_payload.get("ticket_id", "DEF-001")
        self.defect_counts[mod] = self.defect_counts.get(mod, 0) + 1
        self._persist_defect_counts()  # P2-B: survive session restarts

        # Ping-Pong Circuit Breaker: Prevent infinite Dev-QA loops
        if self.defect_counts[mod] > MAX_DEFECT_LOOPBACKS:
            self.update_task_status(mod, "BLOCKED", note=f"QA Rejected {self.defect_counts[mod]} times with ticket {ticket_id}. Suspended to avoid token burnout.")
            return {
                "success": False,
                "action": "ESCALATE_TO_HUMAN",
                "ticket_id": ticket_id,
                "module": mod,
                "defect_count": self.defect_counts[mod],
                "stop_required": True,
                "message": f"Module '{mod}' failed QA acceptance {self.defect_counts[mod]} consecutive times. Auto-ping-pong suspended. Escalating to human user."
            }

        self.update_task_status(mod, "REJECTED_BY_QA", note=f"QA Rejected with ticket {ticket_id} (Attempt {self.defect_counts[mod]}/{MAX_DEFECT_LOOPBACKS})")
        
        return {
            "success": True,
            "action": "DISPATCH_DEV_BUGFIX",
            "ticket_id": ticket_id,
            "module": mod,
            "attempt": self.defect_counts[mod],
            "max_attempts": MAX_DEFECT_LOOPBACKS,
            "next_agent": "squad-dev"
        }


    def handle_signoff(self, receipt_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process QA SignoffReceipt with strict External Anti-Fraud Oracle validation before marking DONE."""
        val = validate_handoff_payload("acceptance", receipt_payload)
        if not val.get("valid"):
            return {
                "success": False,
                "action": "REJECT_SIGNOFF",
                "errors": val.get("errors")
            }
        
        mod = receipt_payload.get("module", "Feature")
        exit_code = receipt_payload.get("runner_exit_code")
        evidence_dir = receipt_payload.get("evidence_dir")

        # Deterministic Oracle Verification (Exit Code & Evidence Directory)
        if exit_code is not None and int(exit_code) != 0:
            err = f"Oracle Rejection: Runner exited with non-zero exit code {exit_code}."
            self.update_task_status(mod, "REJECTED_BY_QA", note=err)
            return {
                "success": False,
                "action": "DISPATCH_DEV_BUGFIX",
                "module": mod,
                "errors": [err],
                "next_agent": "squad-dev"
            }

        if evidence_dir:
            stack = detect_project_stack(workspace_dir=str(self.workspace))
            ev_check = validate_evidence_bundle(evidence_dir, stack=stack)
            if not ev_check.get("valid"):
                errs = ev_check.get("errors", ["Evidence bundle validation failed"])
                self.update_task_status(mod, "REJECTED_BY_QA", note=f"Oracle Rejection: {errs[0]}")
                return {
                    "success": False,
                    "action": "DISPATCH_DEV_BUGFIX",
                    "module": mod,
                    "errors": errs,
                    "next_agent": "squad-dev"
                }

        self.defect_counts.pop(mod, None)
        self._persist_defect_counts()  # P2-B: clear persistent counter on DONE
        self.update_task_status(mod, "DONE", note="Accepted by QA SDET with POAI & Oracle verification.")

        
        return {
            "success": True,
            "action": "MILESTONE_ACCEPTED",
            "module": mod,
            "status": "DONE"
        }



def orchestrate_pipeline(
    user_prompt: Optional[str] = None,
    platform: str = "web",
    workspace: Optional[str] = None
) -> Dict[str, Any]:
    """
    Autonomous closed-loop orchestrator delegating prompt routing to Unified Squad Gate.

    Note: Parameters `progress_file`, `last_status`, and `defect_ticket` were removed (P4-A)
    as they were never consumed. All routing is driven via user_prompt → squad_gate().
    """
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

