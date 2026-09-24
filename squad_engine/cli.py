#!/usr/bin/env python3
"""
Unified CLI Entrypoint for VicnovaLabs Squad Engine.
"""

import sys
import os
import json
import argparse
from pathlib import Path
from .config import get_config, is_qa_screenshot_enabled, set_qa_screenshot_config
from .devices import audit_adb_devices
from .ui_audit import evaluate_ui_fidelity, audit_ui_files
from .triage import (
    dispatch_task,
    triage_intent,
    score_task_complexity,
    get_skills_for_phase,
    audit_recommended_skills
)
from .gate import squad_gate
from .handoffs import validate_handoff_payload, TYPED_HANDOFF_SCHEMAS
from .orchestrator import SquadOrchestrator, orchestrate_pipeline
from .task_plan import (
    init_scoped_task_plan,
    parse_scoped_task_plan,
    update_scoped_task_plan,
    reconcile_scoped_task_plan,
    decompose_large_task
)
from .watchdog import audit_subagents_health
from .progress import parse_project_progress, init_project_progress
from .context_guard import check_context_sufficiency, rank_hypotheses
from .agents_registry import get_agent_definition, get_all_agent_definitions, sync_agents_to_workspace


def main():
    parser = argparse.ArgumentParser(
        prog="squad",
        description="VicnovaLabs Squad — Multi-IDE Autonomous Agent Engine"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: status
    p_status = subparsers.add_parser("status", help="Show squad configuration, devices, and health")
    p_status.add_argument("--json", action="store_true", help="Output status in JSON format")

    # Command: gate (SSOT)
    p_gate = subparsers.add_parser("gate", help="Unified Squad Gate (SSOT) for intent triage, scoped fan-out, and adversarial review")
    p_gate.add_argument("prompt", type=str, help="Prompt text to route through Gate")
    p_gate.add_argument("--domain", "-d", type=str, default=None, help="Active session domain")
    p_gate.add_argument("--platform", "-p", type=str, default="web", help="Target platform (web, mobile)")
    p_gate.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")
    p_gate.add_argument("--mode", "-m", type=str, choices=["suggest", "smart", "auto", "inline"], default=None, help="Squad dispatch mode: suggest (default), smart, auto, or inline")
    p_gate.add_argument("--json", action="store_true", help="Output pure JSON")

    # Command: triage
    p_triage = subparsers.add_parser("triage", help="Classify prompt intent and role")
    p_triage.add_argument("prompt", type=str, help="Prompt text to analyze")
    p_triage.add_argument("--domain", "-d", type=str, default=None, help="Active session domain")

    # Command: suggest
    p_suggest = subparsers.add_parser("suggest", help="Suggest squad agent and relevant skills without auto-dispatching")
    p_suggest.add_argument("prompt", type=str, help="Prompt text to analyze")
    p_suggest.add_argument("--domain", "-d", type=str, default=None, help="Active session domain")
    p_suggest.add_argument("--platform", "-p", type=str, default="web", help="Platform: web or mobile")
    p_suggest.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")
    p_suggest.add_argument("--json", action="store_true", help="Output pure JSON")

    # Command: mode
    p_mode = subparsers.add_parser("mode", help="Get or set squad dispatch mode (suggest, smart, auto, inline)")
    p_mode.add_argument("target_mode", nargs="?", default=None, choices=["suggest", "smart", "auto", "inline", "status"], help="Target dispatch mode")
    p_mode.add_argument("--scope", "-s", choices=["project", "session"], default=None, help="Scope: project or session")
    p_mode.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")
    p_mode.add_argument("--session", type=str, default=None, help="Session ID")
    p_mode.add_argument("--json", action="store_true", help="Output pure JSON")

    # Command: dispatch
    p_dispatch = subparsers.add_parser("dispatch", help="Generate dispatch card and skill directive")
    p_dispatch.add_argument("prompt", type=str, help="Prompt to dispatch")
    p_dispatch.add_argument("--domain", "-d", type=str, default=None, help="Active session domain")
    p_dispatch.add_argument("--platform", "-p", type=str, default="web", help="Platform: web or mobile")
    p_dispatch.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")
    p_dispatch.add_argument("--mode", "-m", type=str, choices=["suggest", "smart", "auto", "inline"], default=None, help="Squad dispatch mode: suggest (default), smart, auto, or inline")
    p_dispatch.add_argument("--json", action="store_true", help="Output pure JSON")

    # Command: complexity
    p_comp = subparsers.add_parser("complexity", help="Score task complexity and model tiering")
    p_comp.add_argument("description", type=str, help="Task description")

    # Command: context
    p_ctx = subparsers.add_parser("context", help="Check context sufficiency")
    p_ctx.add_argument("prompt", type=str, help="Task prompt")
    p_ctx.add_argument("--files", nargs="*", default=[], help="Available files in context")

    # Command: ui-audit
    p_ui = subparsers.add_parser("ui-audit", help="Audit UI fidelity between mock HTML and component")
    p_ui.add_argument("mock", type=str, help="Path or string of reference mock HTML")
    p_ui.add_argument("code", type=str, help="Path or string of component implementation")

    # Command: rank-hypotheses
    p_rank = subparsers.add_parser("rank-hypotheses", help="Rank debugging hypotheses")
    p_rank.add_argument("error_trace", type=str, help="Error message or stack trace")
    p_rank.add_argument("hypotheses", nargs="+", help="List of candidate hypotheses")

    # Command: subagent-watchdog
    p_watch = subparsers.add_parser("subagent-watchdog", help="Audit subagent states and detect hangs/429 errors")
    p_watch.add_argument("subagents_json", type=str, help="JSON string or file path containing list of subagents")
    p_watch.add_argument("--expected-files", nargs="*", default=[], help="Expected output files to verify on disk")

    # Command: progress
    p_prog = subparsers.add_parser("progress", help="Manage and inspect PROJECT_PROGRESS.md")
    prog_subs = p_prog.add_subparsers(dest="progress_command")
    p_prog_stat = prog_subs.add_parser("status", help="Report completion percentage and next steps")
    p_prog_stat.add_argument("--file", "-f", type=str, default=None, help="Path to PROJECT_PROGRESS.md")
    p_prog_init = prog_subs.add_parser("init", help="Initialize PROJECT_PROGRESS.md template")
    p_prog_init.add_argument("name", type=str, help="Project name")
    p_prog_init.add_argument("tasks", nargs="+", help="List of initial tasks/features")
    p_prog_init.add_argument("--file", "-f", type=str, default="PROJECT_PROGRESS.md", help="Target file path")

    # Command: device-audit
    subparsers.add_parser("device-audit", help="Audit connected ADB emulators vs physical devices")

    # Command: validate-handoff
    p_val = subparsers.add_parser("validate-handoff", help="Validate typed handoff JSON payload")
    p_val.add_argument("schema_type", choices=list(TYPED_HANDOFF_SCHEMAS.keys()) + ["manifest", "defect", "decision", "acceptance", "signoff"], help="Schema type")
    p_val.add_argument("payload", type=str, help="JSON file path or inline JSON string")

    # Command: get-schema
    p_sch = subparsers.add_parser("get-schema", help="Get schema definition for handoffs")
    p_sch.add_argument("schema_type", nargs="?", default="all", choices=list(TYPED_HANDOFF_SCHEMAS.keys()) + ["manifest", "defect", "decision", "acceptance", "signoff", "all"], help="Schema type")

    # Command: skills-for
    p_skills = subparsers.add_parser("skills-for", help="List curated skills for a role and phase")
    p_skills.add_argument("role", type=str, help="Squad role (ba, design, dev, debug, qa, marketing)")
    p_skills.add_argument("phase", type=str, nargs="?", default=None, help="Active phase")
    p_skills.add_argument("--platform", "-p", type=str, default="web", help="web or mobile")

    # Command: audit-skills
    p_audit_skills = subparsers.add_parser("audit-skills", help="Audit local IDE skills against recommended squad skills")
    p_audit_skills.add_argument("--json", action="store_true", help="Output pure JSON")

    # Command: list-agents
    subparsers.add_parser("list-agents", help="List all defined squad agents and descriptions")

    # Command: config
    p_config = subparsers.add_parser("config", help="View or modify squad engine configuration")
    p_config.add_argument("key", nargs="?", default="all", choices=["all", "qa-screenshot"], help="Configuration key to inspect or set")
    p_config.add_argument("value", nargs="?", default=None, choices=["on", "off", "true", "false", "enable", "disable"], help="Value to set")
    p_config.add_argument("--workspace", "-w", type=str, default=None, help="Target workspace path")

    # Command: get-agent-def
    p_adef = subparsers.add_parser("get-agent-def", help="Get agent definition JSON for define_subagent")
    p_adef.add_argument("role", type=str, help="Role or agent name")

    # Command: sync-workspace
    p_async = subparsers.add_parser("sync-workspace", help="Sync agent configurations to workspace")
    p_async.add_argument("--workspace", "-w", "--target", type=str, default=None, dest="workspace", help="Target directory")

    # Command: task-plan
    p_task_plan = subparsers.add_parser("task-plan", help="Manage scoped task plans and hierarchical fan-out matrices")
    task_subs = p_task_plan.add_subparsers(dest="task_plan_command")

    p_tp_init = task_subs.add_parser("init", help="Initialize a scoped TASK_PLAN_<id>.md")
    p_tp_init.add_argument("title", type=str, help="Title of scoped task plan")
    p_tp_init.add_argument("subtasks", nargs="+", help="List of subtasks or modules")
    p_tp_init.add_argument("--partition", type=str, default="AUTO", help="Resource partition strategy")
    p_tp_init.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")

    p_tp_status = task_subs.add_parser("status", help="Show current status of scoped task plan")
    p_tp_status.add_argument("--plan", "-p", type=str, default=None, help="Path to specific task plan file")
    p_tp_status.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")

    p_tp_update = task_subs.add_parser("update", help="Update status of a subtask within a scoped plan")
    p_tp_update.add_argument("--plan", "-p", type=str, required=True, help="Path to task plan file")
    p_tp_update.add_argument("--subtask", "-s", type=str, required=True, help="Subtask ID, e.g. ST-01")
    p_tp_update.add_argument("--status", type=str, required=True, help="New status: DONE, READY_FOR_QA, IN_PROGRESS, BLOCKED")
    p_tp_update.add_argument("--note", "-n", type=str, default="", help="Notes or verification evidence")
    p_tp_update.add_argument("--defect", type=str, default=None, help="Defect ticket reference")
    p_tp_update.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")

    p_tp_rec = task_subs.add_parser("reconcile", help="Reconcile completed scoped subtasks into root PROJECT_PROGRESS.md")
    p_tp_rec.add_argument("--plan", "-p", type=str, default=None, help="Path to task plan file")
    p_tp_rec.add_argument("--project-progress", "--progress", "-f", type=str, default=None, dest="progress", help="Path to root PROJECT_PROGRESS.md")
    p_tp_rec.add_argument("--force", action="store_true", help="Force reconcile even if incomplete")
    p_tp_rec.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")

    p_tp_decomp = task_subs.add_parser("decompose", help="Decompose a broad prompt into subtask matrix")
    p_tp_decomp.add_argument("prompt", type=str, help="User prompt to decompose")
    p_tp_decomp.add_argument("--platform", type=str, default="mobile", help="Target platform (mobile, web)")

    # Command: orchestrate
    p_orch = subparsers.add_parser("orchestrate", help="Run autonomous squad orchestrator pipeline")
    p_orch.add_argument("--file", "-f", type=str, default=None, help="Path to PROJECT_PROGRESS.md")
    p_orch.add_argument("--status", "-s", type=str, default=None, help="Last event status (READY_FOR_QA, REJECTED, DONE)")
    p_orch.add_argument("--defect", type=str, default=None, help="Defect ticket details if rejected")
    p_orch.add_argument("--prompt", type=str, default=None, help="User prompt to route through Unified Gate")
    p_orch.add_argument("--platform", "-p", type=str, default="web", help="Platform: web or mobile")
    p_orch.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")

    args = parser.parse_args()
    config = get_config()

    if not args.command or args.command == "status":
        cfg = config.as_dict()
        devs = audit_adb_devices()
        if getattr(args, "json", False):
            print(json.dumps({
                "typesafe_api_key_configured": cfg["has_typesafe_key"],
                "status": "ready (typesafe-jev)" if cfg["has_typesafe_key"] else "fallback-mode (offline-heuristics)",
                "squad_home": cfg["squad_home"],
                "dispatch_mode": cfg.get("dispatch_mode", "suggest"),
                "active_ide": cfg["detected_ide"],
                "devices": devs
            }, indent=2, ensure_ascii=False))
        else:
            print("==================================================")
            print("🚀 VicnovaLabs SQUAD ENGINE — STATUS")
            print("==================================================")
            print(f"Squad Home      : {cfg['squad_home']}")
            print(f"Repo Root       : {cfg['repo_root']}")
            print(f"Agents Dir      : {cfg['agents_dir']}")
            print(f"Skills Dir      : {cfg['skills_dir']}")
            print(f"Dispatch Mode   : {cfg.get('dispatch_mode', 'suggest').upper()} (suggest | smart | auto | inline)")
            print(f"Active IDE      : {cfg['detected_ide']}")
            print(f"TypeSafe API Key: {'CONFIGURED' if cfg['has_typesafe_key'] else 'NOT SET (Offline fallback active)'}")
            print(f"ADB Devices     : {devs['total_count']} ({len(devs['physical_devices'])} Physical, {len(devs['emulators'])} Emulators)")
            print(f"Device Mode     : {devs['mode']}")
            print("==================================================")
        sys.exit(0)

    elif args.command == "gate":
        res = squad_gate(
            args.prompt,
            active_domain=getattr(args, "domain", None),
            platform=getattr(args, "platform", "web"),
            workspace=getattr(args, "workspace", None),
            mode=getattr(args, "mode", None)
        )
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            if res.get("dispatch_card_markdown"):
                print(res["dispatch_card_markdown"])
            print("\n" + json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "triage":
        res = triage_intent(args.prompt, active_domain=getattr(args, "domain", None))
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "suggest":
        res = squad_gate(
            args.prompt,
            active_domain=getattr(args, "domain", None),
            platform=getattr(args, "platform", "web"),
            workspace=getattr(args, "workspace", None),
            mode="suggest"
        )
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            if res.get("dispatch_card_markdown"):
                print(res["dispatch_card_markdown"])
            print("\n" + json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "mode":
        from .mode import get_effective_dispatch_mode, set_dispatch_mode, format_mode_status_card
        if not args.target_mode or args.target_mode == "status":
            info = get_effective_dispatch_mode(workspace=getattr(args, "workspace", None), session_id=getattr(args, "session", None))
            if getattr(args, "json", False):
                print(json.dumps(info, indent=2, ensure_ascii=False))
            else:
                print(format_mode_status_card(info))
        else:
            res = set_dispatch_mode(
                args.target_mode,
                workspace=getattr(args, "workspace", None),
                session_id=getattr(args, "session", None),
                scope=getattr(args, "scope", None)
            )
            if getattr(args, "json", False):
                print(json.dumps(res, indent=2, ensure_ascii=False))
            else:
                if res.get("card_markdown"):
                    print(res["card_markdown"])
                else:
                    print(res.get("message", "Done"))
        sys.exit(0)

    elif args.command == "dispatch":
        res = squad_gate(
            args.prompt,
            active_domain=getattr(args, "domain", None),
            platform=getattr(args, "platform", "web"),
            workspace=getattr(args, "workspace", None),
            mode=getattr(args, "mode", None)
        )
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            if res.get("dispatch_card_markdown"):
                print(res["dispatch_card_markdown"])
            print("\n" + json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "complexity":
        res = score_task_complexity(args.description)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "context":
        res = check_context_sufficiency(args.prompt, args.files)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "ui-audit":
        res = evaluate_ui_fidelity(args.mock, args.code)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "rank-hypotheses":
        res = rank_hypotheses(args.error_trace, args.hypotheses)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "subagent-watchdog":
        res = audit_subagents_health(args.subagents_json, args.expected_files)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "progress":
        if getattr(args, "progress_command", None) == "init":
            res = init_project_progress(args.name, args.tasks, args.file)
        else:
            res = parse_project_progress(getattr(args, "file", None))
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "device-audit":
        res = audit_adb_devices()
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "validate-handoff":
        raw_payload = args.payload
        p_path = Path(raw_payload)
        if p_path.exists() and p_path.is_file():
            payload_data = json.loads(p_path.read_text(encoding="utf-8"))
        else:
            payload_data = json.loads(raw_payload)
        res = validate_handoff_payload(args.schema_type, payload_data)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        if not res.get("valid"):
            sys.exit(1)

    elif args.command == "get-schema":
        st = args.schema_type
        if st == "all":
            print(json.dumps(TYPED_HANDOFF_SCHEMAS, indent=2, ensure_ascii=False))
        else:
            canonical = st.lower()
            if canonical == "signoff":
                canonical = "acceptance"
            print(json.dumps(TYPED_HANDOFF_SCHEMAS.get(canonical, {}), indent=2, ensure_ascii=False))

    elif args.command == "skills-for":
        res = get_skills_for_phase(args.role, args.phase, args.platform)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "audit-skills":
        res = audit_recommended_skills(config)
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print("==================================================")
            print("🧩 VicnovaLabs SQUAD — SKILLS AUDIT")
            print("==================================================")
            print(f"Total Recommended Skills: {res['total_recommended']}")
            print(f"Installed Skills        : {res['installed_count']}")
            print(f"Missing (Optional)      : {res['missing_count']}")
            print("--------------------------------------------------")
            if res["installed"]:
                print("✅ INSTALLED SKILLS:")
                for name, meta in sorted(res["installed"].items()):
                    print(f"  [✓] {name:<24} | {meta['role']}")
                print("")
            if res["missing"]:
                print("⚠️  OPTIONAL RECOMMENDED SKILLS NOT FOUND:")
                for name, meta in sorted(res["missing"].items()):
                    print(f"  [-] {name:<24} | {meta['role']:<16} : {meta['description']}")
                print("")
                print("💡 IMPORTANT NOTE:")
                print("   - All recommended skills above are completely OPTIONAL.")
                print("   - Squad functions normally even without these skills installed.")
                print("   - You can install them into your IDE skills directory or replace them")
                print("     with equivalent skills as required by your project.")
            else:
                print("🎉 All optimal recommended skills are installed in your environment!")
            print("==================================================")

    elif args.command == "list-agents":
        all_defs = get_all_agent_definitions(config)
        result = [{"name": k, "description": v.get("description", "")} for k, v in sorted(all_defs.items())]
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "get-agent-def":
        res = get_agent_definition(args.role, config)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "sync-workspace":
        res = sync_agents_to_workspace(args.workspace, config)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "task-plan":
        cmd = getattr(args, "task_plan_command", "status")
        if cmd == "init":
            res = init_scoped_task_plan(
                title=args.title,
                subtasks=args.subtasks,
                partition_strategy=args.partition,
                workspace=args.workspace
            )
        elif cmd == "status":
            res = parse_scoped_task_plan(args.plan, workspace=args.workspace)
        elif cmd == "update":
            res = update_scoped_task_plan(
                plan_file=args.plan,
                subtask_id=args.subtask,
                status=args.status,
                note=args.note,
                defect_ticket=args.defect,
                workspace=args.workspace
            )
        elif cmd == "reconcile":
            res = reconcile_scoped_task_plan(
                plan_file=args.plan,
                project_progress_file=args.progress,
                force=args.force,
                workspace=args.workspace
            )
        elif cmd == "decompose":
            res = decompose_large_task(args.prompt, platform=args.platform)
        else:
            res = parse_scoped_task_plan(getattr(args, "plan", None), workspace=args.workspace)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "orchestrate":
        res = orchestrate_pipeline(
            progress_file=args.file,
            last_status=args.status,
            defect_ticket=args.defect,
            user_prompt=args.prompt,
            platform=args.platform,
            workspace=args.workspace
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "config":
        if args.key == "qa-screenshot":
            if args.value:
                enabled = args.value.lower() in ["on", "true", "enable"]
                res = set_qa_screenshot_config(enabled, workspace=args.workspace)
                print(f"✅ QA Visual Screenshot Evidence set to: {'ON' if enabled else 'OFF'}")
                print(f"Saved to: {res['saved_to']}")
            else:
                current = is_qa_screenshot_enabled(workspace=args.workspace)
                print(f"📸 QA Visual Screenshot Evidence: {'ON (Auto-enabled)' if current else 'OFF'}")
        else:
            cfg = get_config()
            print("==================================================")
            print("⚙️  VicnovaLabs SQUAD ENGINE — CONFIGURATION")
            print("==================================================")
            print(f"QA Screenshot Evidence : {'ON (Auto-enabled)' if cfg.qa_screenshot_evidence else 'OFF'}")
            print(f"Dispatch Mode          : {cfg.dispatch_mode.upper()}")
            print(f"Squad Home             : {cfg.squad_home}")
            print(f"Repo Root              : {cfg.repo_root}")
            print(f"Active IDE             : {cfg.detect_active_ide()}")
            print("==================================================")


if __name__ == "__main__":
    main()

