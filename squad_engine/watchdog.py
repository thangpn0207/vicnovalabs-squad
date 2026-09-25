#!/usr/bin/env python3
"""
Subagent Watchdog & Zero-Zombie Circuit Breaker.
Monitors running subagent health, detects hung/429 rate limit states, and checks heartbeats.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional


MAX_SUBAGENT_TOOL_CALLS = 25
MAX_SUBAGENT_SCREENSHOTS = 3
MAX_IDENTICAL_TOOL_REPEATS = 3


def audit_transcript_content(lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Inspects transcript entries for runaway tool calls, screenshot loops, and identical command cycles."""
    tool_calls = []
    screencap_count = 0
    commands = []

    for entry in lines:
        tcs = entry.get("tool_calls", [])
        for tc in tcs:
            tname = tc.get("name")
            tool_calls.append(tname)
            args = tc.get("args", {})
            cmd = args.get("CommandLine", "")
            fpath = args.get("AbsolutePath", "")
            if tname == "run_command" and cmd:
                commands.append(cmd.strip())
                if "screencap" in cmd.lower():
                    screencap_count += 1
            elif tname == "view_file" and fpath:
                if any(ext in fpath.lower() for ext in [".png", ".jpg", ".jpeg", ".webp"]):
                    screencap_count += 1

    total_tool_calls = len(tool_calls)
    issues = []

    if total_tool_calls > MAX_SUBAGENT_TOOL_CALLS:
        issues.append({
            "error_type": "EXCESSIVE_TOOL_CALL_LOOP",
            "detail": f"Subagent exceeded max tool call limit ({total_tool_calls} > {MAX_SUBAGENT_TOOL_CALLS}) without completion.",
            "action": "KILL_IMMEDIATELY"
        })

    if screencap_count > MAX_SUBAGENT_SCREENSHOTS:
        issues.append({
            "error_type": "SCREENSHOT_LOOP_VIOLATION",
            "detail": f"Subagent triggered excessive screenshot/view_file calls ({screencap_count} > {MAX_SUBAGENT_SCREENSHOTS}), violating Rule L.3.",
            "action": "KILL_IMMEDIATELY"
        })

    # Check for identical command repeats (3 identical commands in a row)
    if len(commands) >= MAX_IDENTICAL_TOOL_REPEATS:
        for i in range(len(commands) - MAX_IDENTICAL_TOOL_REPEATS + 1):
            window = commands[i:i+MAX_IDENTICAL_TOOL_REPEATS]
            if len(set(window)) == 1:
                issues.append({
                    "error_type": "IDENTICAL_COMMAND_LOOP",
                    "detail": f"Subagent repeated identical command {MAX_IDENTICAL_TOOL_REPEATS} times: '{window[0][:80]}'",
                    "action": "KILL_IMMEDIATELY"
                })
                break

    return {
        "total_tool_calls": total_tool_calls,
        "screencap_count": screencap_count,
        "issues": issues,
        "is_looping": len(issues) > 0
    }


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

        # Deep Transcript Loop Inspection (Rule L.3 & Finite Step Budget)
        t_uri = agent.get("transcript")
        if t_uri:
            t_path = t_uri.replace("file://", "")
            p_trans = Path(t_path)
            if p_trans.exists() and p_trans.is_file():
                try:
                    with open(p_trans, "r", encoding="utf-8") as tf:
                        t_lines = [json.loads(line) for line in tf if line.strip()]
                    t_eval = audit_transcript_content(t_lines)
                    for t_issue in t_eval.get("issues", []):
                        kill_ids.append(cid)
                        issues.append({
                            "conversationId": cid,
                            "role": role,
                            "state": state,
                            "error_type": t_issue["error_type"],
                            "detail": t_issue["detail"],
                            "action": "KILL_IMMEDIATELY"
                        })
                except Exception:
                    pass

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


