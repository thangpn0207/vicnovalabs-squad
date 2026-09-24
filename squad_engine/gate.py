#!/usr/bin/env python3
"""
Unified Squad Gate (SSOT) & Coordination Engine.
Merges intent triage, complexity scoring, scoped task plan initialization,
fan-out multi-agent invocations, and adversarial review into a Single Source of Truth.
"""

import re
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from .devices import audit_adb_devices, is_hardware_constrained, is_device_resume_prompt
from .handoffs import (
    format_dispatch_card,
    format_fanout_dispatch_card,
    format_squad_suggestion_card
)
from .agents_registry import get_agent_definition
from .task_plan import (
    is_single_task,
    is_composite_or_large_task,
    decompose_large_task,
    init_scoped_task_plan
)


FANOUT_TRIGGER_PATTERN = re.compile(
    r"\b(chia\s*việc|song\s*song|nhiều\s*dev|nhiều\s*qa|multi\s*agent|fan[\s-]out|map[\s-]reduce|"
    r"toàn\s*bộ|tất\s*cả|toàn\s*app|batch\s*test|parallel)\b",
    re.IGNORECASE
)

EXPLICIT_SQUAD_TRIGGER_PATTERN = re.compile(
    r"\b("
    r"squad|subagent|sub-agent|đội\s*ngũ|"
    r"gọi\s*(?:squad|agent|subagent|dev[\s-]agent|qa[\s-]agent|design[\s-]agent|debug[\s-]agent|ba[\s-]agent|marketing[\s-]agent)|"
    r"triệu\s*tập|ủy\s*quyền\s*(?:cho\s*agent|cho\s*squad|cho\s*subagent)?|"
    r"dùng\s*(?:squad|subagent|dev[\s-]agent|qa[\s-]agent|design[\s-]agent|debug[\s-]agent|ba[\s-]agent|marketing[\s-]agent)|"
    r"chạy\s*(?:squad|subagent|dev[\s-]agent|qa[\s-]agent|design[\s-]agent|debug[\s-]agent|ba[\s-]agent|marketing[\s-]agent)|"
    r"bật\s*squad|kích\s*hoạt\s*squad|/squad|"
    r"use\s+squad|run\s+squad|call\s+squad|invoke\s+squad|"
    r"use\s+(?:dev|qa|design|debug|ba|marketing)[\s-]agent|"
    r"run\s+(?:dev|qa|design|debug|ba|marketing)[\s-]agent|"
    r"delegate\s+to\s+(?:squad|subagent|agent|(?:dev|qa|design|debug|ba|marketing)[\s-]agent)|"
    r"dispatch\s+squad|spawn\s+subagent"
    r")\b",
    re.IGNORECASE
)


def is_explicit_squad_request(prompt: str) -> bool:
    """Checks if the user explicitly requested squad or subagent delegation."""
    if not prompt:
        return False
    return bool(EXPLICIT_SQUAD_TRIGGER_PATTERN.search(prompt))


def squad_gate(
    prompt: str,
    active_domain: Optional[str] = None,
    platform: str = "web",
    workspace: Optional[str] = None,
    mode: Optional[str] = None
) -> Dict[str, Any]:
    """
    Unified Squad Gate (SSOT).
    Evaluates any prompt and returns a standardized execution contract.
    """
    from .triage import (
        triage_intent,
        score_task_complexity,
        get_skills_for_phase,
        detect_platform,
        OPTION_SELECTION_PATTERN,
        infer_domain_from_history
    )
    from .orchestrator import (
        is_handoff_manifest_prompt,
        requires_adversarial_review,
        detect_adversarial_target
    )

    text = prompt.strip()
    from .config import get_config
    from .mode import get_effective_dispatch_mode, handle_squad_mode_prompt

    # Check if prompt is a mode query / change command (e.g. /vicnolabs-squad mode, /squad smart)
    mode_cmd_result = handle_squad_mode_prompt(text, workspace=workspace)
    if mode_cmd_result:
        return mode_cmd_result

    mode_info = get_effective_dispatch_mode(workspace=workspace, explicit_mode=mode)
    effective_mode = mode_info["mode"]
    is_explicit_squad = is_explicit_squad_request(text)

    # 0. Single-Pass Semantic Assessment (SSOT for all gates)
    from .semantic_evaluator import evaluate_task_semantics
    sem = evaluate_task_semantics(text, active_domain=active_domain, platform=platform)
    detected_p = sem.get("target_platform", "web")
    if platform == "web" and detected_p == "mobile":
        platform = "mobile"

    # 1. Single-task exemption filter
    if is_single_task(text) or sem.get("execution_topology") == "fast_path_inline":
        role = sem.get("assigned_role", "dev")
        comp_val = sem.get("complexity_score", 1)
        skills_info = get_skills_for_phase(role, "coding" if role == "dev" else f"acceptance_{platform}", platform)
        card_md = format_dispatch_card(
            f"{role}-agent", role, "inline_single_task", platform, skills_info["skills"],
            ["SINGLE TASK EXEMPTION: Isolated task executed with zero pipeline overhead."]
        )

        return {
            "status": "success",
            "execution_mode": "inline",
            "decision": "STOP_SINGLE_TASK",
            "role": role,
            "target_agent": f"{role}-agent",
            "platform": platform,
            "active_phase": "inline_single_task",
            "complexity_score": 1,
            "recommended_model": "flash",
            "authorized_skills": skills_info["skills"],
            "subagent_invocation_directive": "Single task exemption. Execute inline with minimal context.",
            "dispatch_card_markdown": card_md,
            "is_single_task": True,
            "auto_chain": False,
            "agent_definition": get_agent_definition(role)
        }

    # 2. Check for Handoff Manifest from Dev -> Dispatch QA Acceptance
    if is_handoff_manifest_prompt(text):
        skills_info = get_skills_for_phase("qa", f"acceptance_{platform}", platform=platform)
        card_md = format_dispatch_card(
            "qa-agent", "qa", f"acceptance_{platform}", platform, skills_info["skills"],
            [
                "DEV HANDOFF DETECTED: Main Agent MUST NOT execute or apply code inline.",
                "PROOF-OF-ACTIVE-INTERACTION: Execute black-box acceptance testing with fresh entity.",
                "DIFF COVERAGE VERIFICATION: Verify line coverage >= 85% and branch coverage >= 80%.",
                "MANDATORY RUNTIME LOG AUDIT: Verify terminal/logcat for unhandled silent exceptions."
            ]
        )
        return {
            "status": "success",
            "execution_mode": "subagent",
            "decision": "DISPATCH_QA_ACCEPTANCE",
            "role": "qa",
            "target_agent": "qa-agent",
            "platform": platform,
            "active_phase": f"acceptance_{platform}",
            "complexity_score": 3,
            "recommended_model": "inherit",
            "authorized_skills": skills_info["skills"],
            "subagent_invocation_directive": f"Dev completed handoff. Run QA acceptance testing on {platform}.",
            "dispatch_card_markdown": card_md,
            "auto_chain": True,
            "agent_definition": get_agent_definition("qa")
        }

    # 3. Check for Device Resume Checkpoint
    if is_device_resume_prompt(text):
        audit = audit_adb_devices()
        if audit["total_count"] == 0:
            return {
                "status": "checkpoint",
                "execution_mode": "pause",
                "decision": "AWAIT_DEVICE",
                "role": None,
                "target_agent": None,
                "auto_chain": False,
                "checkpoint_status": "DEVICE_NOT_FOUND",
                "hardware_audit": audit,
                "instruction": (
                    "No connected devices or emulators found in `adb devices`. "
                    "Please launch an emulator or connect a device via USB with 'USB Debugging' enabled. "
                    "Then type 'resume' or 'connected' to continue testing."
                )
            }
        target_device = audit["physical_devices"][0] if audit["has_physical_device"] else audit["emulators"][0]
        dev_serial = target_device["serial"]
        dev_desc = target_device.get("model", "Android Device")
        skills_info = get_skills_for_phase("qa", "acceptance_mobile", platform="mobile")
        return {
            "status": "success",
            "execution_mode": "subagent",
            "decision": "RESUME_DEVICE_QA",
            "role": "qa",
            "target_agent": "qa-agent",
            "platform": "mobile",
            "active_phase": "acceptance_mobile",
            "auto_chain": True,
            "hardware_audit": audit,
            "authorized_skills": skills_info["skills"],
            "instruction": f"Target device ready: {dev_serial} ({dev_desc}). Resume acceptance testing immediately."
        }

    # 4. Check for Hardware Constraint & Cooperative Device Checkpoint
    if is_hardware_constrained(text):
        audit = audit_adb_devices()
        if not audit["has_physical_device"] and not audit.get("is_headless"):
            return {
                "status": "checkpoint",
                "execution_mode": "pause",
                "decision": "AWAIT_PHYSICAL_DEVICE",
                "role": None,
                "target_agent": None,
                "auto_chain": False,
                "checkpoint_status": "COOPERATIVE_PAUSE",
                "hardware_audit": audit,
                "instruction": (
                    "Feature strictly requires physical hardware (Camera / Optical QR / P2P / Bluetooth). "
                    "Paused at Cooperative Hardware Checkpoint awaiting physical device connection."
                )
            }
        elif audit.get("is_headless"):
            skills_info = get_skills_for_phase("qa", "acceptance_mobile", platform="mobile")
            return {
                "status": "success",
                "execution_mode": "subagent",
                "decision": "DISPATCH_HEADLESS_QA",
                "role": "qa",
                "target_agent": "qa-agent",
                "platform": "mobile",
                "active_phase": "acceptance_mobile",
                "auto_chain": True,
                "hardware_audit": audit,
                "authorized_skills": skills_info["skills"]
            }
        elif audit["mode"] == "dual_device_hybrid" or audit["can_run_dual_device"]:
            skills_info = get_skills_for_phase("qa", "hybrid_dual_device_qa", platform="mobile")
            return {
                "status": "success",
                "execution_mode": "subagent",
                "decision": "DISPATCH_HYBRID_QA",
                "role": "qa",
                "target_agent": "qa-agent",
                "platform": "mobile",
                "active_phase": "hybrid_dual_device_qa",
                "auto_chain": True,
                "hardware_audit": audit,
                "authorized_skills": skills_info["skills"]
            }

    # 5. Composite / Large Task or Explicit Fan-Out Request -> Scoped Fan-Out Pipeline
    # Explicit fan-out commands always take precedence; composite tasks fan out unless they are high-impact architecture requiring red team review first.
    is_explicit_fanout = bool(FANOUT_TRIGGER_PATTERN.search(text))
    if not OPTION_SELECTION_PATTERN.search(text) and (is_explicit_fanout or (is_composite_or_large_task(text) and not requires_adversarial_review(text))):
        decomposition = decompose_large_task(text, platform=platform, workspace=workspace)
        plan_info = init_scoped_task_plan(
            title=decomposition["title"],
            subtasks=decomposition["subtasks"],
            partition_strategy=decomposition["partition_strategy"],
            workspace=workspace
        )

        fanout_invocations = []
        for st in plan_info["subtasks"]:
            role_target = st.get("role", decomposition["role"])
            agent_target = st.get("target_agent", f"{role_target}-agent")
            phase_to_use = f"acceptance_{platform}" if role_target == "qa" else "coding"
            skills_info = get_skills_for_phase(role_target, phase_to_use, platform=platform)

            directive = (
                f"🎯 [MANDATORY SCOPED SUBAGENT DIRECTIVE FOR {agent_target}]:\n"
                f"- Scoped Task Plan: `{plan_info['file_path']}`\n"
                f"- Assigned Subtask ID: `{st['id']}` ({st['title']})\n"
                f"- Resource Partition: `{st['partition']}`\n"
                f"- Active Phase: '{phase_to_use}' ({platform.upper()})\n"
                f"- Authorized Skills: {skills_info['skills']}\n"
                f"- CONSTRAINT: Update ONLY `{plan_info['file_name']}`. DO NOT edit root PROJECT_PROGRESS.md.\n"
                f"- CONSTRAINT: Stay strictly within Resource Partition `{st['partition']}`.\n"
            )

            fanout_invocations.append({
                "TypeName": agent_target,
                "Role": f"{agent_target} - {st['id']}: {st['title']}",
                "Prompt": (
                    f"{directive}\n\n"
                    f"Execute implementation/verification for subtask `{st['id']}: {st['title']}`. "
                    f"Upon completion, update status in `{plan_info['file_name']}` via:\n"
                    f"`squad task-plan update --plan {plan_info['file_path']} --subtask {st['id']} --status READY_FOR_QA --note 'Self-test passed'`."
                )
            })

        card_md = format_fanout_dispatch_card(
            decomposition["title"],
            plan_info["file_path"],
            plan_info["subtasks"]
        )

        return {
            "status": "success",
            "execution_mode": "fanout",
            "decision": "SCOPED_FANOUT",
            "role": decomposition["role"],
            "target_agent": f"{decomposition['role']}-agent",
            "platform": platform,
            "plan_id": plan_info["plan_id"],
            "plan_file": plan_info["file_path"],
            "plan_name": plan_info["file_name"],
            "total_subtasks": plan_info["total_subtasks"],
            "partition_strategy": decomposition["partition_strategy"],
            "subtasks": plan_info["subtasks"],
            "fanout_invocations": fanout_invocations,
            "dispatch_card_markdown": card_md,
            "auto_chain": True,
            "agent_definition": get_agent_definition(decomposition["role"])
        }

    # 6. Check for Selective Adversarial Review Gate
    if requires_adversarial_review(text):
        target_info = detect_adversarial_target(text)
        target_domain = target_info["target_domain"]
        skeptic_agent = target_info["skeptic_agent"]
        role = skeptic_agent.replace("-agent", "")

        phase = "investigation" if role == "debug" else ("coding" if role == "dev" else f"acceptance_{platform}")
        skills_info = get_skills_for_phase(role, phase, platform=platform)

        constraints = [
            f"ADVERSARIAL REVIEW ACTIVE: Role [{skeptic_agent}] conducts red team review on [{target_domain}].",
            "STRUCTURED CRITIQUE: Must emit JSON conforming to schema 'critique' (AdversarialCritique).",
            "FOCUS: Uncover latent edge cases, race conditions, auth bypasses, and untestable specs."
        ]
        card_md = format_dispatch_card(skeptic_agent, role, phase, platform, skills_info["skills"], constraints)

        return {
            "status": "success",
            "execution_mode": "subagent",
            "decision": "DISPATCH_ADVERSARIAL_REVIEW",
            "role": role,
            "target_agent": skeptic_agent,
            "platform": platform,
            "active_phase": phase,
            "complexity_score": 4,
            "recommended_model": "pro",
            "authorized_skills": skills_info["skills"],
            "subagent_invocation_directive": (
                f"Conduct adversarial skeptic review on target domain '{target_domain}'. "
                f"Emit typed critique schema."
            ),
            "dispatch_card_markdown": card_md,
            "adversarial_review_active": True,
            "target_domain": target_domain,
            "skeptic_agent": skeptic_agent,
            "schema_contract": "critique",
            "auto_chain": True,
            "agent_definition": get_agent_definition(role)
        }



    # 7. Check for Option Selection
    if OPTION_SELECTION_PATTERN.search(text):
        effective_domain = active_domain or infer_domain_from_history()
        target_agent = f"{effective_domain}-agent"
        phase = "coding" if effective_domain == "dev" else f"acceptance_{platform}"
        skills_info = get_skills_for_phase(effective_domain, phase, platform)
        skills = skills_info.get("skills", [])
        agent_def = get_agent_definition(effective_domain)

        # In suggest mode, execute inline directly unless explicit squad is requested or mode is auto
        if effective_mode == "auto" or is_explicit_squad:
            card_md = format_dispatch_card(target_agent, effective_domain, phase, platform, skills, [
                "OPTION SELECTION GUARD: Dispatching explicitly chosen option to domain specialist."
            ])
            return {
                "status": "success",
                "execution_mode": "subagent",
                "decision": "DISPATCH_OPTION_SELECTION",
                "dispatch_mode": effective_mode,
                "role": effective_domain,
                "target_agent": target_agent,
                "platform": platform,
                "active_phase": phase,
                "complexity_score": 3,
                "recommended_model": "inherit",
                "authorized_skills": skills,
                "subagent_invocation_directive": f"Option selected. Execute chosen option under domain '{effective_domain}' directly in filesystem.",
                "dispatch_card_markdown": card_md,
                "auto_chain": True,
                "agent_definition": agent_def
            }
        else:
            card_md = format_squad_suggestion_card(
                target_agent, effective_domain, phase, platform, skills, 2,
                f"Executing selected option under domain '{effective_domain}'."
            )
            return {
                "status": "success",
                "execution_mode": "inline",
                "decision": "INLINE_OPTION_SELECTION",
                "dispatch_mode": effective_mode,
                "squad_suggested": True,
                "role": effective_domain,
                "target_agent": target_agent,
                "platform": platform,
                "active_phase": phase,
                "complexity_score": 2,
                "recommended_model": "flash",
                "authorized_skills": skills,
                "subagent_invocation_directive": f"Execute chosen option under domain '{effective_domain}' inline.",
                "dispatch_card_markdown": card_md,
                "auto_chain": False,
                "agent_definition": agent_def
            }

    # 8. Standard Semantic Triage Dispatch
    triage_res = triage_intent(text, active_domain)
    comp_res = score_task_complexity(text)
    role = triage_res["role"]
    target_agent = f"{role}-agent"
    phase = "coding" if role == "dev" else f"acceptance_{platform}"
    skills_info = get_skills_for_phase(role, phase, platform)
    skills = skills_info.get("skills", [])
    agent_def = get_agent_definition(role)
    comp_score = comp_res.get("complexity_score", 2)

    # Decide execution mode based on effective_mode & explicit triggers
    if is_explicit_squad:
        mode_decision = "subagent"
        decision_label = "DISPATCH_EXPLICIT_SQUAD"
        auto_chain = True
        is_suggested = False
        card_md = format_dispatch_card(target_agent, role, phase, platform, skills, [
            f"EXPLICIT SQUAD SUMMON: Delegating directly to [{target_agent}].",
            "ZERO CODE-OFFLOADING: Subagent must write all modified files directly to filesystem.",
            "SELF-TEST OBLIGATION: Must run self-tests before reporting back."
        ])
    elif effective_mode == "auto":
        is_inline = False
        if re.search(r"\b(typo|rename|format|comment|small|1 line|single line|docstring|explain|what is|how to)\b", text):
            is_inline = True
        elif comp_score == 1 and role not in ["design", "debug", "qa"]:
            is_inline = True

        if re.search(r"\b(build|feature|refactor|migration|investigate|mockup|html|trace|failing|error|bug|test|suite|multi|redesign|giao\s*diện|thiết\s*kế|option\s*[0-9a-e]|phương\s*án\s*[0-9a-e]|nghiệm\s*thu|kiểm\s*thử|playwright|emulator|máy\s*ảo|acceptance)\b", text):
            is_inline = False

        mode_decision = "inline" if is_inline else "subagent"
        decision_label = "DISPATCH_PROMPT"
        auto_chain = not is_inline
        is_suggested = False
        role_constraints = [
            "ZERO CODE-OFFLOADING: Subagent must write all modified files directly to filesystem.",
            "DIFF COVERAGE GATE: Must achieve Line >= 85%, Branch >= 80% with coverage_report.",
            "NO PRODUCTION PASS ASSIGNMENT: Never self-grant [x] DONE. Mark [-] READY_FOR_QA."
        ] if role == "dev" else [
            "BLACK-BOX SDET: QA tests independently with POAI, never blindly re-executing dev tests.",
            "STRICT BAN ON SOURCE CODE EDITING: Do NOT edit production code files in lib/, src/, app/.",
            "PROOF-OF-ACTIVE-INTERACTION: All target devices must be actively driven with fresh payloads.",
            "MANDATORY RUNTIME LOG AUDIT: Must inspect logcat/terminal logs for silent errors."
        ] if role == "qa" else []
        card_md = format_dispatch_card(target_agent, role, phase, platform, skills, role_constraints)
    elif effective_mode == "smart":
        if comp_score >= 4:
            mode_decision = "subagent"
            decision_label = "DISPATCH_HIGH_COMPLEXITY"
            auto_chain = True
            is_suggested = False
            card_md = format_dispatch_card(target_agent, role, phase, platform, skills, [
                f"SMART SQUAD ACTIVATION: High complexity ({comp_score}/5) warrants dedicated subagent."
            ])
        else:
            mode_decision = "inline"
            decision_label = "SUGGEST_SQUAD"
            auto_chain = False
            is_suggested = True
            card_md = format_squad_suggestion_card(target_agent, role, phase, platform, skills, comp_score)
    elif effective_mode == "inline":
        mode_decision = "inline"
        decision_label = "INLINE_EXECUTION"
        auto_chain = False
        is_suggested = False
        card_md = ""
    else:  # effective_mode == "suggest" (DEFAULT)
        mode_decision = "inline"
        decision_label = "SUGGEST_SQUAD"
        auto_chain = False
        is_suggested = True
        card_md = format_squad_suggestion_card(target_agent, role, phase, platform, skills, comp_score)

    return {
        "status": "success",
        "execution_mode": mode_decision,
        "decision": decision_label,
        "dispatch_mode": effective_mode,
        "squad_suggested": is_suggested,
        "role": role,
        "target_agent": target_agent,
        "platform": platform,
        "active_phase": phase,
        "complexity_score": comp_score,
        "recommended_model": comp_res.get("recommended_model", "flash" if mode_decision == "inline" else "inherit"),
        "authorized_skills": skills,
        "subagent_invocation_directive": f"Execute task under role '{role}' in phase '{phase}' with authorized skills: {skills}.",
        "dispatch_card_markdown": card_md,
        "auto_chain": auto_chain,
        "agent_definition": agent_def
    }
