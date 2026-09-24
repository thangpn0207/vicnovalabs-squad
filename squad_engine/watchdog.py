#!/usr/bin/env python3
"""
Subagent Watchdog & Zero-Zombie Circuit Breaker.
Monitors running subagent health, detects hung/429 rate limit states, and checks heartbeats.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional


def audit_subagents_health(subagents_input: Any, expected_files: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Subagent Watchdog & Zero-Zombie Circuit Breaker:
    - Inspects subagents reported by `manage_subagents(Action='list')`
    - Identifies errored states (RESOURCE_EXHAUSTED / 429, timeout, crash)
    - Verifies expected output files on disk (Heartbeat check)
    - Returns kill list, stop requirement, and detailed diagnostic alert.
    """
    if isinstance(subagents_input, str):
        try:
            p = Path(subagents_input)
            if p.exists() and p.is_file():
                with open(p, "r", encoding="utf-8") as f:
                    subagents = json.load(f)
            else:
                subagents = json.loads(subagents_input)
        except Exception:
            subagents = []
    elif isinstance(subagents_input, list):
        subagents = subagents_input
    else:
        subagents = []

    kill_ids = []
    issues = []
    is_quota_exhausted = False

    for agent in subagents:
        if not isinstance(agent, dict):
            continue
        cid = agent.get("conversationId", "unknown")
        role = agent.get("role", agent.get("type", "unknown"))
        state = str(agent.get("state", "")).lower()
        detail = str(agent.get("stateDetail", "")).lower()

        # Check for provider 429 / RESOURCE_EXHAUSTED
        if "resource_exhausted" in detail or "429" in detail or "quota" in detail:
            is_quota_exhausted = True
            kill_ids.append(cid)
            issues.append({
                "conversationId": cid,
                "role": role,
                "state": state,
                "error_type": "RESOURCE_EXHAUSTED_429",
                "detail": agent.get("stateDetail", "Provider quota exceeded / rate limit (429)"),
                "action": "KILL_IMMEDIATELY"
            })
        elif state == "waiting_for_dependents":
            kill_ids.append(cid)
            issues.append({
                "conversationId": cid,
                "role": role,
                "state": state,
                "error_type": "ORPHANED_DEPENDENTS_HANG",
                "detail": agent.get("stateDetail") or "Subagent blocked by unreleased background child tasks or processes.",
                "action": "KILL_IMMEDIATELY"
            })
        elif state == "canceling":
            kill_ids.append(cid)
            issues.append({
                "conversationId": cid,
                "role": role,
                "state": state,
                "error_type": "CANCELING_HANG",
                "detail": agent.get("stateDetail") or "Subagent stuck in canceling state without graceful termination.",
                "action": "KILL_IMMEDIATELY"
            })
        elif state == "errored" or "exception" in detail or "crash" in detail or "failed" in detail:
            kill_ids.append(cid)
            issues.append({
                "conversationId": cid,
                "role": role,
                "state": state,
                "error_type": "PROCESS_ERROR",
                "detail": agent.get("stateDetail", "Subagent execution errored"),
                "action": "KILL_IMMEDIATELY"
            })

    # Output file heartbeat check
    missing_files = []
    if expected_files:
        for ef in expected_files:
            p = Path(ef)
            if not p.exists() or p.stat().st_size == 0:
                missing_files.append(ef)

    has_issue = len(issues) > 0 or len(missing_files) > 0

    alert_lines = []
    if is_quota_exhausted:
        alert_lines.append("🚨 **QUOTA EXHAUSTION DETECTED (HTTP 429 / RESOURCE_EXHAUSTED)**")
        alert_lines.append("Subagent encountered TPM/RPM rate limits from backend provider and process is hung.")
    elif len(issues) > 0:
        alert_lines.append("⚠️ **SUBAGENT ERROR OR HANG DETECTED**")

    for iss in issues:
        alert_lines.append(f"- Subagent `{iss['role']}` (`{iss['conversationId']}`): {iss['error_type']} -> {iss['detail']}")

    if missing_files:
        alert_lines.append(f"- **Missing expected output files (Heartbeat Failure)**: {missing_files}")

    if has_issue:
        alert_lines.append("\n🛑 **Mandatory Action**: Errored subagents queued for termination. STOP PROCESS IMMEDIATELY to notify user. DO NOT retry silently.")

    return {
        "status": "ACTION_REQUIRED" if has_issue else "HEALTHY",
        "stop_required": has_issue,
        "is_quota_exhausted": is_quota_exhausted,
        "kill_conversation_ids": sorted(list(set(kill_ids))),
        "issues": issues,
        "missing_files": missing_files,
        "alert_message": "\n".join(alert_lines) if alert_lines else "All subagents operating normally."
    }


def reap_zombie_subagents(subagents_input: Any) -> List[str]:
    """Identify and return list of conversation IDs that must be reaped/killed immediately."""
    audit = audit_subagents_health(subagents_input)
    return audit.get("kill_conversation_ids", [])


