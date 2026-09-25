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
    mode: Optional[str] = None,
    touched_files: Optional[List[str]] = None,
    diff_lines_override: Optional[int] = None
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
    from .passive_scanner import run_passive_scanner

    mode_info = get_effective_dispatch_mode(workspace=workspace, explicit_mode=mode)
    effective_mode = mode_info["mode"]

    # 0a. Check if prompt is /squad status
    if re.search(r"^(?:/squad|squad)\s+status\b", text, re.IGNORECASE):
        scan = run_passive_scanner(workspace_dir=workspace, touched_files=touched_files, diff_lines_override=diff_lines_override)
        return {
            "status": "success",
            "execution_mode": "inline",
            "decision": "STATUS",
            "dispatch_mode": effective_mode,
            "tier_0_scan": scan.to_dict(),
            "auto_chain": False
        }

    # Check if prompt is a mode query / change command (e.g. /vicnolabs-squad mode, /squad smart)
    mode_cmd_result = handle_squad_mode_prompt(text, workspace=workspace)
    if mode_cmd_result:
        return mode_cmd_result

    # Check if prompt is an agent setting / permission repair request (Self-Healing Gateway)
    fix_match = re.search(
        r"\b("
        r"fix[-\s_]?agent(?:[-\s_]?setting)?|fix[-\s_]?setting|fix[-\s_]?permission|"
        r"sửa\s*(?:lỗi\s*)?(?:permistion|permission|quyền|setting|cấu\s*hình)\s*(?:của|cho)?\s*(?:agent|squad|dev|subagent)?|"
        r"kiểm\s*tra\s*(?:lại\s*)?(?:permistion|permission|quyền|setting|cấu\s*hình)\s*(?:của|cho)?\s*(?:agent|squad|dev|subagent)?"
        r")\b",
        text,
        re.IGNORECASE
    )
    if fix_match:
        from .fix_agent_setting import fix_agent_setting, format_fix_report_markdown
        res = fix_agent_setting(workspace=workspace)
        card_md = format_fix_report_markdown(res)
        return {
            "status": "success",
            "execution_mode": "inline",
            "decision": "FIX_AGENT_SETTING",
            "action": "fix",
            "details": res,
            "dispatch_card_markdown": card_md,
            "auto_chain": False
        }

    # 0b. Tier 0 Passive Scanner (Pure structural/path matching, zero LLM cost)
    passive_scan = run_passive_scanner(
        workspace_dir=workspace,
        touched_files=touched_files,
        diff_lines_override=diff_lines_override
    )

    # 0c. Command Surface: /squad full vs /squad <role>
    is_full_pipeline = bool(re.search(
        r"\b(/squad\s+full|squad\s+full|full\s+pipeline|toàn\s*bộ\s*pipeline|run\s+it\s+through\s+qa)\b",
        text,
        re.IGNORECASE
    ))

    single_role_match = re.search(
        r"^(?:/squad|squad)\s+(dev|qa|design|debug|ba|marketing)\b",
        text,
        re.IGNORECASE
    ) or re.search(
        r"\b(?:/squad|squad)\s+(dev|qa|design|debug|ba|marketing)\b",
        text,
        re.IGNORECASE
    )
    explicit_single_role = single_role_match.group(1).lower() if single_role_match else None
    is_explicit_squad = is_explicit_squad_request(text) and not explicit_single_role

    # Dynamic Stack Detection
    from .semantic_evaluator import evaluate_task_semantics
    from .stack_detector import detect_project_stack
    from .scope_evaluator import evaluate_scope_risk
    sem = evaluate_task_semantics(text, active_domain=active_domain, platform=platform)
    detected_p = sem.get("target_platform", "web")
    if platform == "web" and detected_p == "mobile":
        platform = "mobile"

    stack = detect_project_stack(workspace_dir=workspace, prompt=text)
    if platform == "web" and stack.category == "mobile":
        platform = "mobile"

    # Tier A Scope & Risk Evaluation (Deterministic File/Diff Check)
    scope_risk = evaluate_scope_risk(workspace_dir=workspace, prompt=text, touched_files=touched_files)

    # Batch 7: Tier 1 Manual On-Demand Single Role Execution (/squad <role>)
    if explicit_single_role and not is_full_pipeline:
        role = explicit_single_role
        target_agent = f"squad-{role}"
        phase = "coding" if role == "dev" else f"acceptance_{platform}"
        skills_info = get_skills_for_phase(role, phase, platform=platform)
        card_md = format_dispatch_card(
            target_agent, role, phase, platform, skills_info["skills"],
            ["TIER 1 MANUAL ON-DEMAND: Single-agent execution with zero auto-chaining."],
            stack_name=stack.name
        )
        return {
            "status": "success",
            "execution_mode": "subagent" if effective_mode == "auto" else "inline",
            "decision": f"MANUAL_ON_DEMAND_{role.upper()}",
            "dispatch_mode": effective_mode,
            "role": role,
            "target_agent": target_agent,
            "platform": platform,
            "stack": stack.to_dict(),
            "active_phase": phase,
            "complexity_score": 2,
            "recommended_model": "inherit",
            "authorized_skills": skills_info["skills"],
            "subagent_invocation_directive": f"Execute task under single role '{role}' ({stack.name}). Do not chain to downstream agents.",
            "dispatch_card_markdown": card_md,
            "tier_0_scan": passive_scan.to_dict(),
            "notice": passive_scan.notice,
            "soft_suggestion": passive_scan.notice if passive_scan.decision == "escalate_suggested" else None,
            "auto_chain": False,
            "agent_definition": get_agent_definition(role)
        }

    # 1. Single-task exemption filter (Fast-Path Inline) - applies when user didn't explicitly request squad/full
    if (passive_scan.decision == "fast_path" or scope_risk.is_fast_path or is_single_task(text, workspace=workspace) or sem.get("execution_topology") == "fast_path_inline") and not is_explicit_squad and not is_full_pipeline:
        role = sem.get("assigned_role", "dev")
        comp_val = sem.get("complexity_score", 1)
        skills_info = get_skills_for_phase(role, "coding" if role == "dev" else f"acceptance_{platform}", platform)
        card_md = format_dispatch_card(
            f"{role}-agent", role, "inline_single_task", platform, skills_info["skills"],
            ["SINGLE TASK EXEMPTION: Isolated task executed with zero pipeline overhead."],
            stack_name=stack.name
        )

        return {
            "status": "success",
            "execution_mode": "inline",
            "decision": "STOP_SINGLE_TASK",
            "role": role,
            "target_agent": f"squad-{role}",
            "platform": platform,
            "stack": stack.to_dict(),
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
            "squad-qa", "qa", f"acceptance_{platform}", platform, skills_info["skills"],
            [
                "DEV HANDOFF DETECTED: Main Agent MUST NOT execute or apply code inline.",
                "PROOF-OF-ACTIVE-INTERACTION: Execute black-box acceptance testing with fresh entity.",
                "DIFF COVERAGE VERIFICATION: Verify line coverage >= 85% and branch coverage >= 80%.",
                "MANDATORY RUNTIME LOG AUDIT: Verify terminal/logcat for unhandled silent exceptions."
            ],
            stack_name=stack.name
        )
        return {
            "status": "success",
            "execution_mode": "subagent",
            "decision": "DISPATCH_QA_ACCEPTANCE",
            "role": "qa",
            "target_agent": "squad-qa",
            "platform": platform,
            "stack": stack.to_dict(),
            "active_phase": f"acceptance_{platform}",
            "complexity_score": 3,
            "recommended_model": "inherit",
            "authorized_skills": skills_info["skills"],
            "subagent_invocation_directive": (
                f"Dev completed handoff. Run QA acceptance testing on {platform} ({stack.name}) using the Test Runner Script pattern. "
                f"DO NOT read application source code ({', '.join(stack.blackbox_globs)}). Execute verification_command ({stack.test_runner}) or standalone test runner script in test/."
            ),
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
            "target_agent": "squad-qa",
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
                "target_agent": "squad-qa",
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
                "target_agent": "squad-qa",
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
            agent_target = st.get("target_agent", f"squad-{role_target}")
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
            "target_agent": f"squad-{decomposition['role']}",
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

    # 6. Check for Selective Adversarial Review Gate (Driven by Tier A/B and Passive Scanner)
    is_sensitive_change = scope_risk.requires_adversarial_review or passive_scan.signals.get("auth_security", False) or (
        scope_risk.delegate_to_tier_b and sem.get("adversarial_risk") == "requires_skeptic_review"
    )
    if is_sensitive_change:
        target_info = detect_adversarial_target(text)
        target_domain = target_info["target_domain"]
        skeptic_agent = target_info["skeptic_agent"]
        role = skeptic_agent.replace("squad-", "").replace("-agent", "")

        phase = "investigation" if role == "debug" else ("coding" if role == "dev" else f"acceptance_{platform}")
        skills_info = get_skills_for_phase(role, phase, platform=platform)

        constraints = [
            f"ADVERSARIAL REVIEW ACTIVE: [{skeptic_agent}] on [{target_domain}].",
            "STRUCTURED CRITIQUE: Must emit JSON conforming to schema 'critique' (AdversarialCritique)."
        ]
        card_md = format_dispatch_card(skeptic_agent, role, phase, platform, skills_info["skills"], constraints)
        if target_domain == "security" or "auth" in text.lower():
            notice = "💡 Notice: this change touches Auth/Security. Run full squad review? (/squad full, or continue as-is)"
        elif passive_scan.notice:
            notice = passive_scan.notice
        elif "migration" in text.lower() or "database" in text.lower():
            notice = "💡 Notice: schema/migration change detected. Run squad-qa for migration safety check? (/squad qa)"
        else:
            notice = f"💡 Notice: this change touches {target_domain.capitalize() if target_domain else 'Architecture'}. Run full squad review? (/squad full, or continue as-is)"

        # Non-blocking unless explicitly summoned or mode is auto
        if not is_explicit_squad and not is_full_pipeline and effective_mode != "auto":
            return {
                "status": "success",
                "execution_mode": "inline",
                "decision": "INLINE_WITH_SOFT_SUGGESTION",
                "dispatch_mode": effective_mode,
                "role": "dev" if role == "debug" else role,
                "target_agent": f"squad-{role}",
                "platform": platform,
                "stack": stack.to_dict(),
                "active_phase": "coding" if role == "debug" else phase,
                "complexity_score": 2,
                "recommended_model": "flash",
                "authorized_skills": skills_info["skills"],
                "subagent_invocation_directive": "Execute inline with awareness of sensitive domain.",
                "soft_suggestion": notice,
                "notice": notice,
                "tier_0_scan": passive_scan.to_dict(),
                "adversarial_review_active": True,
                "target_domain": target_domain,
                "skeptic_agent": skeptic_agent,
                "schema_contract": "critique",
                "dispatch_card_markdown": card_md,
                "auto_chain": False,
                "agent_definition": get_agent_definition(role)
            }

        return {
            "status": "success",
            "execution_mode": "subagent",
            "decision": "DISPATCH_ADVERSARIAL_REVIEW",
            "role": role,
            "target_agent": f"squad-{role}",
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
            "tier_0_scan": passive_scan.to_dict(),
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
        target_agent = f"squad-{effective_domain}"
        phase = "coding" if effective_domain == "dev" else f"acceptance_{platform}"
        skills_info = get_skills_for_phase(effective_domain, phase, platform)
        skills = skills_info.get("skills", [])
        agent_def = get_agent_definition(effective_domain)

        # In suggest mode, execute inline directly unless explicit squad is requested or mode is auto
        if effective_mode == "auto" or is_explicit_squad:
            card_md = format_dispatch_card(target_agent, effective_domain, phase, platform, skills, [
                "OPTION SELECTION GUARD: Dispatching explicitly chosen option to domain specialist."
            ], stack_name=stack.name)
            return {
                "status": "success",
                "execution_mode": "subagent",
                "decision": "DISPATCH_OPTION_SELECTION",
                "dispatch_mode": effective_mode,
                "role": effective_domain,
                "target_agent": target_agent,
                "platform": platform,
                "stack": stack.to_dict(),
                "active_phase": phase,
                "complexity_score": 3,
                "recommended_model": "inherit",
                "authorized_skills": skills,
                "subagent_invocation_directive": f"Option selected. Execute chosen option under domain '{effective_domain}' ({stack.name}) directly in filesystem.",
                "dispatch_card_markdown": card_md,
                "tier_0_scan": passive_scan.to_dict(),
                "notice": passive_scan.notice,
                "auto_chain": True,
                "agent_definition": agent_def
            }
        else:
            card_md = format_squad_suggestion_card(
                target_agent, effective_domain, phase, platform, skills, 2,
                f"Executing selected option under domain '{effective_domain}'.",
                stack_name=stack.name
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
                "stack": stack.to_dict(),
                "active_phase": phase,
                "complexity_score": 2,
                "recommended_model": "flash",
                "authorized_skills": skills,
                "subagent_invocation_directive": f"Execute chosen option under domain '{effective_domain}' ({stack.name}) inline.",
                "dispatch_card_markdown": card_md,
                "tier_0_scan": passive_scan.to_dict(),
                "notice": passive_scan.notice,
                "auto_chain": False,
                "agent_definition": agent_def
            }

    # 8. Standard Semantic Triage Dispatch
    triage_res = triage_intent(text, active_domain)
    comp_res = score_task_complexity(text)
    role = triage_res["role"]
    target_agent = f"squad-{role}"
    phase = "coding" if role == "dev" else f"acceptance_{platform}"
    skills_info = get_skills_for_phase(role, phase, platform)
    skills = skills_info.get("skills", [])
    agent_def = get_agent_definition(role)
    comp_score = comp_res.get("complexity_score", 2)




    # Decide execution mode based on effective_mode & explicit triggers
    if is_explicit_squad or is_full_pipeline:
        mode_decision = "subagent"
        decision_label = "DISPATCH_FULL_PIPELINE" if is_full_pipeline else "DISPATCH_EXPLICIT_SQUAD"
        auto_chain = True
        is_suggested = False
        card_md = format_dispatch_card(target_agent, role, phase, platform, skills, [
            f"{'EXPLICIT FULL PIPELINE REQUEST' if is_full_pipeline else 'EXPLICIT SQUAD SUMMON'}: Delegating to [{target_agent}].",
            "ZERO CODE-OFFLOADING: Subagent must write all modified files directly to filesystem.",
            "SELF-TEST OBLIGATION: Must run self-tests before reporting back."
        ], stack_name=stack.name)
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
            f"STRICT BAN ON SOURCE CODE EDITING: Do NOT edit production code files ({', '.join(stack.blackbox_globs)}).",
            "PROOF-OF-ACTIVE-INTERACTION: All target devices must be actively driven with fresh payloads.",
            "MANDATORY RUNTIME LOG AUDIT: Must inspect runtime logs for silent errors."
        ] if role == "qa" else []
        card_md = format_dispatch_card(target_agent, role, phase, platform, skills, role_constraints, stack_name=stack.name)
    elif effective_mode == "smart":
        if comp_score >= 4:
            mode_decision = "subagent"
            decision_label = "DISPATCH_HIGH_COMPLEXITY"
            auto_chain = True
            is_suggested = False
            card_md = format_dispatch_card(target_agent, role, phase, platform, skills, [
                f"SMART SQUAD ACTIVATION: High complexity ({comp_score}/5) warrants dedicated subagent."
            ], stack_name=stack.name)
        else:
            mode_decision = "inline"
            decision_label = "SUGGEST_SQUAD"
            auto_chain = False
            is_suggested = True
            card_md = format_squad_suggestion_card(target_agent, role, phase, platform, skills, comp_score, stack_name=stack.name)
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
        card_md = format_squad_suggestion_card(target_agent, role, phase, platform, skills, comp_score, stack_name=stack.name)

    return {
        "status": "success",
        "execution_mode": mode_decision,
        "decision": decision_label,
        "dispatch_mode": effective_mode,
        "squad_suggested": is_suggested,
        "role": role,
        "target_agent": target_agent,
        "platform": platform,
        "stack": stack.to_dict(),
        "active_phase": phase,
        "complexity_score": comp_score,
        "recommended_model": comp_res.get("recommended_model", "flash" if mode_decision == "inline" else "inherit"),
        "authorized_skills": skills,
        "subagent_invocation_directive": (
            f"Execute task under role '{role}' in phase '{phase}' ({stack.name}) with authorized skills: {skills}."
            + (f" [QA MANDATE]: DO NOT read application source code ({', '.join(stack.blackbox_globs)}). Follow the Test Runner Script pattern: execute tests via a standalone runner command in test/ and pipe logs with grep." if role == "qa" else "")
        ),
        "dispatch_card_markdown": card_md,
        "tier_0_scan": passive_scan.to_dict(),
        "notice": passive_scan.notice,
        "soft_suggestion": passive_scan.notice if passive_scan.decision == "escalate_suggested" else None,
        "auto_chain": auto_chain,
        "agent_definition": agent_def
    }
