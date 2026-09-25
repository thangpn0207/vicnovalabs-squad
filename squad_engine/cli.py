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
    prune_scoped_plans,
    decompose_large_task
)
from .watchdog import audit_subagents_health
from .progress import parse_project_progress, init_project_progress
from .context_guard import check_context_sufficiency, rank_hypotheses
from .agents_registry import get_agent_definition, get_all_agent_definitions, sync_agents_to_workspace
from .fix_agent_setting import fix_agent_setting, format_fix_report_markdown


def main():
    # ==========================================
    # 0. TRANSPARENT LEGACY ALIASES (Zero-Clutter Redirection)
    # ==========================================
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "gate":
            sys.argv[1] = "dispatch"
        elif cmd == "stream":
            sys.argv[1] = "office"
        elif cmd == "plan":
            sys.argv[1] = "task-plan"
        elif cmd in ["fix-agent-setting", "fix-agents", "repair-agent-setting", "fix-setting", "fix"]:
            sys.argv[1] = "fix-agent-setting"
        elif cmd == "suggest":
            sys.argv = [sys.argv[0], "dispatch", "--mode", "suggest"] + sys.argv[2:]
        elif cmd in ["dev", "qa", "design", "debug", "ba", "marketing"]:
            prompt_arg = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else ""
            extra_args = [a for a in sys.argv[2:] if a != prompt_arg]
            sys.argv = [sys.argv[0], "dispatch", f"/squad {cmd} {prompt_arg}".strip()] + extra_args
        elif cmd == "full":
            prompt_arg = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else ""
            extra_args = [a for a in sys.argv[2:] if a != prompt_arg]
            sys.argv = [sys.argv[0], "dispatch", f"/squad full {prompt_arg}".strip()] + extra_args
        elif cmd == "triage":
            prompt = sys.argv[2] if len(sys.argv) > 2 else ""
            res = triage_intent(prompt)
            print(json.dumps(res, indent=2, ensure_ascii=False))
            sys.exit(0)
        elif cmd == "complexity":
            desc = sys.argv[2] if len(sys.argv) > 2 else ""
            print(json.dumps(score_task_complexity(desc), indent=2, ensure_ascii=False))
            sys.exit(0)
        elif cmd == "skills-for":
            role = sys.argv[2] if len(sys.argv) > 2 else "dev"
            phase = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("-") else None
            plat = "web"
            if "--platform" in sys.argv:
                plat = sys.argv[sys.argv.index("--platform") + 1]
            elif "-p" in sys.argv:
                plat = sys.argv[sys.argv.index("-p") + 1]
            print(json.dumps(get_skills_for_phase(role, phase, platform=plat), indent=2, ensure_ascii=False))
            sys.exit(0)
        elif cmd == "context":
            prompt = sys.argv[2] if len(sys.argv) > 2 else ""
            print(json.dumps({"prompt": prompt, "status": "sufficient"}, indent=2, ensure_ascii=False))
            sys.exit(0)
        elif cmd == "stack":
            ws = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else None
            prompt_val = ""
            if "--prompt" in sys.argv:
                prompt_val = sys.argv[sys.argv.index("--prompt") + 1]
            from .stack_detector import detect_project_stack
            res = detect_project_stack(ws or os.getcwd(), prompt=prompt_val)
            print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
            sys.exit(0)

    parser = argparse.ArgumentParser(
        prog="squad",
        description="VicnovaLabs Squad — Multi-IDE Autonomous Agent Engine"
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>", help="Available subcommands")

    # ==========================================
    # 1. PRIMARY AI RUNTIME GATEWAY (SSOT)
    # ==========================================
    p_dispatch = subparsers.add_parser(
        "dispatch",
        help="⚡ [AI Gateway] Primary All-in-One Gateway (SSOT). Evaluates user intent, devices, skills, and mode in a single call."
    )
    p_dispatch.add_argument("prompt", type=str, help="Prompt to dispatch")
    p_dispatch.add_argument("--domain", "-d", type=str, default=None, help="Active session domain")
    p_dispatch.add_argument("--platform", "-p", type=str, default="web", help="Platform: web or mobile")
    p_dispatch.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")
    p_dispatch.add_argument("--mode", "-m", type=str, choices=["suggest", "smart", "auto", "inline"], default=None, help="Squad dispatch mode: suggest (default), smart, auto, or inline")
    p_dispatch.add_argument("--json", action="store_true", help="Output pure JSON")

    p_mode = subparsers.add_parser(
        "mode",
        help="🔄 [Mode Control] View or set squad dispatch mode (suggest, smart, auto, inline)"
    )
    p_mode.add_argument("target_mode", nargs="?", default=None, choices=["suggest", "smart", "auto", "inline", "status"], help="Target dispatch mode")
    p_mode.add_argument("--scope", "-s", choices=["project", "session"], default=None, help="Scope: project or session")
    p_mode.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")
    p_mode.add_argument("--session", type=str, default=None, help="Session ID")
    p_mode.add_argument("--json", action="store_true", help="Output pure JSON")

    # ==========================================
    # 2. SPECIALIZED SUBAGENT TOOLS (In-Phase Tools)
    # ==========================================
    p_val = subparsers.add_parser(
        "validate-handoff",
        help="📋 [Subagent Tool] Validate typed handoff JSON payload (manifest, defect, decision, acceptance)"
    )
    p_val.add_argument("schema_type", choices=list(TYPED_HANDOFF_SCHEMAS.keys()) + ["manifest", "defect", "decision", "acceptance", "signoff"], help="Schema type")
    p_val.add_argument("payload", type=str, help="JSON file path or inline JSON string")
    p_val.add_argument("--strict-evidence", action="store_true", help="Enforce runner exit code and evidence validation")
    p_val.add_argument("--strict-traceability", action="store_true", help="Enforce requirement_ids on manifest/acceptance")
    p_val.add_argument("--exit-code", type=int, default=None, help="Runner script exit code for strict evidence validation")
    p_val.add_argument("--evidence-dir", type=str, default=None, help="Evidence directory for strict evidence validation")

    p_sch = subparsers.add_parser(
        "get-schema",
        help="📐 [Subagent Tool] Get JSON schema contract definition for typed handoffs"
    )
    p_sch.add_argument("schema_type", nargs="?", default="all", choices=list(TYPED_HANDOFF_SCHEMAS.keys()) + ["manifest", "defect", "decision", "acceptance", "signoff", "all"], help="Schema type")

    p_ui = subparsers.add_parser(
        "ui-audit",
        help="🎨 [Subagent Tool] Audit UI fidelity between mock HTML and component (Design & QA)"
    )
    p_ui.add_argument("mock", type=str, help="Path or string of reference mock HTML")
    p_ui.add_argument("code", type=str, help="Path or string of component implementation")

    p_rank = subparsers.add_parser(
        "rank-hypotheses",
        help="🔍 [Subagent Tool] Rank debugging hypotheses with empirical evidence (Debug Agent)"
    )
    p_rank.add_argument("error_trace", type=str, help="Error message or stack trace")
    p_rank.add_argument("hypotheses", nargs="+", help="List of candidate hypotheses")

    p_watch = subparsers.add_parser(
        "subagent-watchdog",
        help="🛡️ [Subagent Tool] Audit subagent health, detect hangs, 429 quota exhaustion, and runaway loops"
    )
    p_watch.add_argument("subagents_json", type=str, help="JSON string or file path containing list of subagents")
    p_watch.add_argument("--expected-files", nargs="*", default=[], help="Expected output files to verify on disk")

    # ==========================================
    # 3. DEVELOPER DIAGNOSTICS & SYSTEM STATUS
    # ==========================================
    p_status = subparsers.add_parser(
        "status",
        help="🩺 [Diagnostic] Show squad configuration, devices, and engine health"
    )
    p_status.add_argument("--json", action="store_true", help="Output status in JSON format")

    subparsers.add_parser(
        "device-audit",
        help="📱 [Diagnostic] Audit connected ADB emulators vs physical devices (Manual diagnostic)"
    )

    p_preflight = subparsers.add_parser(
        "preflight",
        help="📱 [EDQA] Run ADB hardware preflight checks on target device"
    )
    p_preflight.add_argument("serial", nargs="?", default="emulator-5554", help="Target ADB serial (default: emulator-5554)")
    p_preflight.add_argument("--package", "-p", type=str, default="", help="Target package ID to check")
    p_preflight.add_argument("--min-storage", type=int, default=500, help="Minimum free storage in MB (default: 500)")
    p_preflight.add_argument("--json", action="store_true", help="Output pure JSON")


    p_audit_skills = subparsers.add_parser(
        "audit-skills",
        help="🧩 [Diagnostic] Audit local IDE skills against recommended squad skills"
    )
    p_audit_skills.add_argument("--json", action="store_true", help="Output pure JSON")

    p_config = subparsers.add_parser(
        "config",
        help="⚙️ [Diagnostic] View or modify squad engine configuration"
    )
    p_config.add_argument("key", nargs="?", default="all", choices=["all", "qa-screenshot"], help="Configuration key to inspect or set")
    p_config.add_argument("value", nargs="?", default=None, choices=["on", "off", "true", "false", "enable", "disable"], help="Value to set")
    p_config.add_argument("--workspace", "-w", type=str, default=None, help="Target workspace path")

    p_prog = subparsers.add_parser(
        "progress",
        help="📊 [Diagnostic] Manage and inspect PROJECT_PROGRESS.md"
    )
    prog_subs = p_prog.add_subparsers(dest="progress_command")
    p_prog_stat = prog_subs.add_parser("status", help="Report completion percentage and next steps")
    p_prog_stat.add_argument("--file", "-f", type=str, default=None, help="Path to PROJECT_PROGRESS.md")
    p_prog_init = prog_subs.add_parser("init", help="Initialize PROJECT_PROGRESS.md template")
    p_prog_init.add_argument("name", type=str, help="Project name")
    p_prog_init.add_argument("tasks", nargs="+", help="List of initial tasks/features")
    p_prog_init.add_argument("--file", "-f", type=str, default="PROJECT_PROGRESS.md", help="Target file path")

    subparsers.add_parser(
        "list-agents",
        help="👥 [Diagnostic] List all defined squad agents and descriptions"
    )

    p_stack = subparsers.add_parser(
        "stack",
        help="🔍 [Stack Detector] Detect project tech stack, language, test runner, selectors, and MCP tools"
    )
    p_stack.add_argument("workspace", nargs="?", default=None, help="Workspace directory (defaults to cwd)")
    p_stack.add_argument("--prompt", "-p", type=str, default="", help="Optional prompt for semantic fallback")
    p_stack.add_argument("--json", action="store_true", help="Output pure JSON")

    # Command: get-agent-def
    p_adef = subparsers.add_parser("get-agent-def", help="Get agent definition JSON for define_subagent")
    p_adef.add_argument("role", type=str, help="Role or agent name")
    p_adef.add_argument("--full", action="store_true", help="Output full system prompt without truncation")

    # Command: sync-workspace
    p_async = subparsers.add_parser("sync-workspace", help="Sync agent configurations to workspace")
    p_async.add_argument("--workspace", "-w", "--target", type=str, default=None, dest="workspace", help="Target directory")

    # Command: fix-agent-setting (Self-Healing Gateway)
    p_fix_setting = subparsers.add_parser(
        "fix-agent-setting",
        aliases=["fix-agents", "repair-agent-setting", "fix-setting", "fix"],
        help="🔧 [Self-Healing] Audit and repair agent permissions, workspace settings, and static traps"
    )
    p_fix_setting.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory to audit and repair")
    p_fix_setting.add_argument("--dry-run", action="store_true", help="Audit without modifying filesystem")
    p_fix_setting.add_argument("--force", "-f", action="store_true", help="Force recreate settings and re-initialize")
    p_fix_setting.add_argument("--json", action="store_true", help="Output results in pure JSON format")

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

    p_tp_prune = task_subs.add_parser("prune", help="Prune obsolete scoped task plans to prevent cache bloat")
    p_tp_prune.add_argument("--keep", "-k", type=int, default=10, help="Maximum number of recent plans to retain (default: 10)")
    p_tp_prune.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")

    # Command: orchestrate
    p_orch = subparsers.add_parser("orchestrate", help="Run autonomous squad orchestrator pipeline")
    p_orch.add_argument("--file", "-f", type=str, default=None, help="Path to PROJECT_PROGRESS.md")
    p_orch.add_argument("--status", "-s", type=str, default=None, help="Last event status (READY_FOR_QA, REJECTED, DONE)")
    p_orch.add_argument("--defect", type=str, default=None, help="Defect ticket details if rejected")
    p_orch.add_argument("--receipt", type=str, default=None, help="SignoffReceipt JSON string or file path to evaluate and mark DONE")
    p_orch.add_argument("--manifest", type=str, default=None, help="HandoffManifest JSON string or file path to transition to READY_FOR_QA")
    p_orch.add_argument("--prompt", type=str, default=None, help="User prompt to route through Unified Gate")
    p_orch.add_argument("--platform", "-p", type=str, default="web", help="Platform: web or mobile")
    p_orch.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")

    # Command: test-run
    p_testrun = subparsers.add_parser(
        "test-run",
        help="🧪 [Test Harness] Generate and execute a standalone test runner script adapted to detected stack"
    )
    p_testrun.add_argument("--stack", type=str, default="auto",
                           choices=["auto", "flutter", "web_frontend", "react_native", "node_backend",
                                    "python", "go", "rust", "android_native", "ios_native", "generic"],
                           help="Stack profile (auto-detects from workspace)")
    p_testrun.add_argument("--suite", type=str, default="app_launch", help="Test suite / journey name")
    p_testrun.add_argument("--device", type=str, default="emulator-5554", help="Target device serial")
    p_testrun.add_argument("--package", type=str, default="", help="App package name (mobile)")
    p_testrun.add_argument("--url", type=str, default="http://localhost:3000", help="Target URL (web)")
    p_testrun.add_argument("--evidence-dir", type=str, default="", help="Evidence output directory")
    p_testrun.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")
    p_testrun.add_argument("--dry-run", action="store_true", help="Generate script without executing")

    # Command: validate-evidence
    p_valev = subparsers.add_parser(
        "validate-evidence",
        help="🔍 [Oracle] Validate evidence directory against External Anti-Fraud Oracle"
    )
    p_valev.add_argument("evidence_dir", type=str, help="Path to evidence directory")
    p_valev.add_argument("--stack", type=str, default=None, help="Stack profile for error signature matching")
    p_valev.add_argument("--max-age", type=int, default=300, help="Max evidence age in seconds (default: 300)")
    p_valev.add_argument("--json", action="store_true", help="Output pure JSON")

    # Command: crawl (Crawl4AI)
    p_crawl = subparsers.add_parser(
        "crawl",
        help="🌐 [Crawl4AI Scraper] Fetch URL and extract clean, noise-free Markdown"
    )
    p_crawl.add_argument("url", type=str, help="URL to crawl and extract")
    p_crawl.add_argument("--max-tokens", "-t", type=int, default=1500, help="Max token budget (default: 1500)")
    p_crawl.add_argument("--output", "-o", type=str, default=None, help="Output markdown file path")
    p_crawl.add_argument("--json", action="store_true", help="Output pure JSON")

    # Command: memory (OpenClaw)
    p_mem = subparsers.add_parser(
        "memory",
        help="🧠 [OpenClaw Memory] Manage 3-tier persistent memory (SOUL, MEMORY, WORKING) and context compactor"
    )
    p_mem.add_argument("action", choices=["status", "record", "compact", "working", "supersede"], help="Memory action")
    p_mem.add_argument("text", nargs="?", default="", help="Insight text to record, topic to supersede, or text to compact")
    p_mem.add_argument("--topic", type=str, default="Architectural Insight", help="Topic for recorded insight")
    p_mem.add_argument("--tier", type=str, default="inferred", choices=["verified", "decision", "inferred", "historical", "superseded"], help="Trust tier for recorded insight")
    p_mem.add_argument("--reason", type=str, default="", help="Reason for superseding insight")
    p_mem.add_argument("--workspace", "-w", type=str, default=None, help="Workspace directory")
    p_mem.add_argument("--json", action="store_true", help="Output pure JSON")

    # Command: worktree (Superpowers)
    p_wt = subparsers.add_parser(
        "worktree",
        help="🌲 [Superpowers Worktrees] Manage isolated Git worktrees for parallel subagents"
    )
    p_wt.add_argument("action", choices=["create", "list", "remove", "merge"], help="Worktree action")
    p_wt.add_argument("slug", nargs="?", default="", help="Task slug for worktree")
    p_wt.add_argument("--repo", "-r", type=str, default=None, help="Repository root directory")
    p_wt.add_argument("--test-command", "-t", type=str, default=None, help="Command to run before merging (test-before-merge policy)")
    p_wt.add_argument("--json", action="store_true", help="Output pure JSON")

    # Command: office
    p_office = subparsers.add_parser(
        "office",
        help="🏢 [Virtual Office] Launch Virtual Squad Office & Real-Time Telemetry Dashboard"
    )
    p_office.add_argument("action", nargs="?", default="start", choices=["start", "stop", "status"], help="Action: start (default), stop, or status")
    p_office.add_argument("--port", "-p", type=int, default=7777, help="Server port (default: 7777)")
    p_office.add_argument("--no-browser", action="store_true", help="Run without auto-opening browser tab")
    p_office.add_argument("--json", action="store_true", help="Output pure JSON")

    args = parser.parse_args()
    config = get_config()

    if not args.command or args.command == "status":
        from .passive_scanner import run_passive_scanner
        from .mode import get_effective_dispatch_mode
        ws = os.getcwd()
        mode_info = get_effective_dispatch_mode(workspace=ws)
        scan = run_passive_scanner(workspace_dir=ws)
        if getattr(args, "json", False):
            print(json.dumps({
                "mode": mode_info["mode"],
                "tier_0_scan": scan.to_dict()
            }, indent=2, ensure_ascii=False))
        else:
            print("==================================================")
            print("🚀 VicnovaLabs SQUAD STATUS")
            print("==================================================")
            print(f"Mode            : {mode_info['mode']}")
            print(f"Tier 0 Decision : {scan.decision}")
            print(f"Signals         : {json.dumps(scan.signals)}")
            print(f"Diff Size       : {scan.size.get('files_changed', 0)} files, {scan.size.get('total_diff_lines', 0)} lines")
            if scan.notice:
                print(f"Notice          : {scan.notice}")
            print("==================================================")
        sys.exit(0)


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
        summary_keys = [
            "status", "execution_mode", "decision", "dispatch_mode", "role",
            "target_agent", "platform", "active_phase", "complexity_score",
            "authorized_skills", "subagent_invocation_directive", "auto_chain",
            "tier_0_scan", "notice"
        ]
        compact = {k: res[k] for k in summary_keys if k in res}
        if res.get("squad_suggested"):
            compact["squad_suggested"] = True
        if res.get("checkpoint_status"):
            compact["checkpoint_status"] = res["checkpoint_status"]
        if res.get("instruction"):
            compact["instruction"] = res["instruction"]
        if res.get("soft_suggestion"):
            compact["soft_suggestion"] = res["soft_suggestion"]
        if res.get("notice"):
            compact["notice"] = res["notice"]
        if res.get("agent_definition"):
            adef = res["agent_definition"]
            compact["agent_definition"] = {
                "name": adef.get("name"),
                "enable_write_tools": adef.get("enable_write_tools"),
                "enable_mcp_tools": adef.get("enable_mcp_tools"),
                "enable_subagent_tools": adef.get("enable_subagent_tools"),
                "system_prompt": (adef.get("system_prompt", "")[:120] + "... (fetch full via: squad get-agent-def <role>)")
            }

        if getattr(args, "json", False):
            print(json.dumps(compact, indent=2, ensure_ascii=False))
        else:
            # Immersive Stealth Mode: only print markdown card for subagent or fanout
            if res.get("execution_mode") in ["subagent", "fanout"] and res.get("dispatch_card_markdown"):
                print(res["dispatch_card_markdown"])
            if res.get("soft_suggestion"):
                print(f"\n{res['soft_suggestion']}")
            elif res.get("notice"):
                print(f"\n{res['notice']}")
            print("\n" + json.dumps(compact, indent=2, ensure_ascii=False))


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

    elif args.command == "preflight":
        from .devices import run_adb_preflight
        res = run_adb_preflight(args.serial, package_id=args.package, min_storage_mb=args.min_storage)
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print("==================================================")
            print(f"📱 ADB HARDWARE PREFLIGHT — [{args.serial}]")
            print("==================================================")
            print(f"Status           : {'READY (PASS)' if res['ready'] else 'NOT READY (FAIL)'}")
            for k, v in res.get("checks", {}).items():
                print(f"  • {k:20}: {v}")
            if res.get("errors"):
                print("❌ Errors:")
                for err in res["errors"]:
                    print(f"  - {err}")
            print("==================================================")
        sys.exit(0 if res["ready"] else 1)


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
        if not getattr(args, "full", False):
            def_dir = Path("/tmp/squad_agent_defs")
            def_dir.mkdir(parents=True, exist_ok=True)
            def_file = def_dir / f"{args.role}.md"
            def_file.write_text(res.get("system_prompt", ""), encoding="utf-8")

            compact_res = {
                "name": res.get("name"),
                "description": res.get("description"),
                "enable_write_tools": res.get("enable_write_tools"),
                "enable_mcp_tools": res.get("enable_mcp_tools"),
                "enable_subagent_tools": res.get("enable_subagent_tools"),
                "system_prompt": res.get("system_prompt", "")[:120] + f"... (full definition written to file://{def_file}, use --full to display)",
                "system_prompt_path": str(def_file)
            }
            print(json.dumps(compact_res, indent=2, ensure_ascii=False))
        else:
            print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "sync-workspace":
        res = sync_agents_to_workspace(args.workspace, config)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command in ["fix-agent-setting", "fix-agents", "repair-agent-setting", "fix-setting", "fix"]:
        res = fix_agent_setting(
            workspace=getattr(args, "workspace", None),
            dry_run=getattr(args, "dry_run", False),
            force=getattr(args, "force", False)
        )
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(format_fix_report_markdown(res))

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
        elif cmd == "prune":
            res = prune_scoped_plans(max_keep=getattr(args, "keep", 10), workspace=args.workspace)
        else:
            res = parse_scoped_task_plan(getattr(args, "plan", None), workspace=args.workspace)
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "orchestrate":
        if getattr(args, "receipt", None):
            raw = args.receipt
            if os.path.exists(raw):
                with open(raw, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            else:
                payload = json.loads(raw)
            orch = SquadOrchestrator(workspace_path=args.workspace)
            res = orch.handle_signoff(payload)
        elif getattr(args, "manifest", None):
            raw = args.manifest
            if os.path.exists(raw):
                with open(raw, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            else:
                payload = json.loads(raw)
            orch = SquadOrchestrator(workspace_path=args.workspace)
            res = orch.handle_handoff(payload)
        else:
            res = orchestrate_pipeline(
                progress_file=args.file,
                last_status=args.status,
                defect_ticket=args.defect,
                user_prompt=args.prompt,
                platform=args.platform,
                workspace=args.workspace
            )
        print(json.dumps(res, indent=2, ensure_ascii=False))

    elif args.command == "stack":
        from .stack_detector import detect_project_stack
        ws = args.workspace or os.getcwd()
        profile = detect_project_stack(ws, prompt=getattr(args, "prompt", ""))
        print(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False))

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

    elif args.command == "test-run":
        from .test_harness import generate_test_runner_script
        from .stack_detector import detect_project_stack, STACK_PROFILES
        import subprocess
        import tempfile

        # Resolve stack
        if args.stack == "auto":
            ws = getattr(args, "workspace", None) or os.getcwd()
            stack = detect_project_stack(ws)
        else:
            stack = STACK_PROFILES.get(args.stack, STACK_PROFILES["generic"])

        # Default journey steps based on suite
        journey_steps = []
        if args.suite == "app_launch":
            if stack.category == "mobile":
                journey_steps = [
                    {"action": "launch"},
                    {"action": "logcat_check"}
                ]
            else:
                journey_steps = [
                    {"action": "navigate", "target": args.url},
                    {"action": "assert_text", "target": "Welcome"}
                ]
        else:
            journey_steps = [{"action": "launch"}] if stack.category == "mobile" else [
                {"action": "navigate", "target": args.url}
            ]

        result = generate_test_runner_script(
            stack=stack,
            journey_steps=journey_steps,
            evidence_dir=getattr(args, "evidence_dir", "") or "",
            package=args.package,
            device_serial=args.device,
            url=args.url
        )

        if getattr(args, "dry_run", False):
            print(f"--- Generated Script: {result['filename']} ---")
            print(result["script_content"])
            print(f"--- Evidence Dir: {result['evidence_dir']} ---")
            print(f"--- Execution Command: {result['execution_command']} ---")
        else:
            script_dir = Path(tempfile.mkdtemp(prefix="squad_runner_"))
            script_path = script_dir / result["filename"]
            script_path.write_text(result["script_content"], encoding="utf-8")
            script_path.chmod(0o755)

            print(f"🧪 Executing test runner: {script_path}")
            print(f"📁 Evidence dir: {result['evidence_dir']}")
            print(f"📊 Stack: {stack.name}")
            print("---")

            proc = subprocess.run(
                ["python3", str(script_path)],
                capture_output=True,
                text=True,
                timeout=120
            )

            stdout_lines = proc.stdout.strip().splitlines()
            if len(stdout_lines) > 40:
                for line in stdout_lines[:5]:
                    print(line)
                print(f"... ({len(stdout_lines) - 10} lines truncated)")
                for line in stdout_lines[-5:]:
                    print(line)
            else:
                print(proc.stdout)

            if proc.stderr.strip():
                stderr_lines = proc.stderr.strip().splitlines()
                for line in stderr_lines[-10:]:
                    print(f"STDERR: {line}")

            print(f"\n--- Exit Code: {proc.returncode} ---")
            sys.exit(proc.returncode)

    elif args.command == "validate-evidence":
        from .evidence_oracle import validate_evidence_bundle
        from .stack_detector import STACK_PROFILES

        stack = None
        if args.stack:
            stack = STACK_PROFILES.get(args.stack)

        result = validate_evidence_bundle(
            evidence_dir=args.evidence_dir,
            stack=stack,
            max_age_seconds=getattr(args, "max_age", 300)
        )

        if getattr(args, "json", False):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            status_icon = "✅ VALID" if result["valid"] else "❌ INVALID"
            print(f"{status_icon} — Evidence: {args.evidence_dir}")
            print(f"  Files: {result['total_files']} | Screenshots: {result['screenshots']} | Logs: {result['log_files']}")
            if result.get("screenshot_pairs"):
                for pair in result["screenshot_pairs"]:
                    status = "✓ mutated" if pair["mutated"] else "✗ IDENTICAL"
                    print(f"  Step {pair['step']}: {status} (pre={pair['pre_hash'][:8]}... post={pair['post_hash'][:8]}...)")
            if result["errors"]:
                print(f"\n  Errors ({len(result['errors'])}):")
                for err in result["errors"]:
                    print(f"    ✗ {err}")
            if result["warnings"]:
                print(f"\n  Warnings ({len(result['warnings'])}):")
                for w in result["warnings"]:
                    print(f"    ⚠ {w}")
            sys.exit(0 if result["valid"] else 1)

    elif args.command == "crawl":
        from .crawler import crawl_url_to_markdown
        res = crawl_url_to_markdown(args.url, max_tokens=args.max_tokens)
        if args.output and res.get("markdown"):
            Path(args.output).write_text(res["markdown"], encoding="utf-8")
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            if res.get("status") in ["success", "cached"]:
                print(res["markdown"])
            else:
                print(f"Error crawling {args.url}: {res.get('error')}", file=sys.stderr)
                sys.exit(1)

    elif args.command == "memory":
        from .memory import SquadMemory, compact_context_text
        mem = SquadMemory(workspace_path=args.workspace)
        if args.action == "status":
            bundle = mem.get_summary_bundle()
            print(json.dumps(bundle, indent=2, ensure_ascii=False))
        elif args.action == "record":
            if not args.text:
                print("Error: Text required for memory record", file=sys.stderr)
                sys.exit(1)
            tier_val = getattr(args, "tier", "inferred")
            mem.append_long_term_insight(args.topic, args.text, trust_level=tier_val)
            print(json.dumps({"status": "recorded", "topic": args.topic, "tier": tier_val}, indent=2, ensure_ascii=False))
        elif args.action == "supersede":
            topic_to_supersede = args.text or args.topic
            count = mem.supersede_insight(topic_to_supersede, reason=getattr(args, "reason", ""))
            print(json.dumps({"status": "superseded", "topic": topic_to_supersede, "superseded_count": count}, indent=2, ensure_ascii=False))
        elif args.action == "compact":
            compacted = compact_context_text(args.text)
            if getattr(args, "json", False):
                print(json.dumps({"original_chars": len(args.text), "compacted_chars": len(compacted), "compacted": compacted}, indent=2, ensure_ascii=False))
            else:
                print(compacted)
        elif args.action == "working":
            print(mem.read_working())

    elif args.command == "worktree":
        from .worktrees import create_task_worktree, list_task_worktrees, remove_task_worktree, merge_task_worktree
        repo = args.repo or os.getcwd()
        if args.action == "list":
            trees = list_task_worktrees(repo)
            print(json.dumps(trees, indent=2, ensure_ascii=False))
        elif args.action == "create":
            if not args.slug:
                print("Error: Task slug required for worktree create", file=sys.stderr)
                sys.exit(1)
            res = create_task_worktree(repo, args.slug)
            print(json.dumps(res, indent=2, ensure_ascii=False))
            if not res.get("success"):
                sys.exit(1)
        elif args.action == "remove":
            res = remove_task_worktree(repo, args.slug)
            print(json.dumps(res, indent=2, ensure_ascii=False))
        elif args.action == "merge":
            res = merge_task_worktree(repo, args.slug, test_command=getattr(args, "test_command", None))
            print(json.dumps(res, indent=2, ensure_ascii=False))
            if not res.get("success"):
                sys.exit(1)

    elif args.command == "office":
        from .server import SquadOfficeServer
        squad_dir = os.path.join(os.getcwd(), ".squad")
        pid_file = os.path.join(squad_dir, "office.pid")

        if args.action == "status":
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, "r") as f:
                        info = json.load(f)
                    print(json.dumps({"status": "running", **info}, indent=2))
                except Exception:
                    print(json.dumps({"status": "unknown", "pid_file_exists": True}, indent=2))
            else:
                print(json.dumps({"status": "stopped"}, indent=2))
            sys.exit(0)

        elif args.action == "stop":
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, "r") as f:
                        info = json.load(f)
                    pid = info.get("pid")
                    if pid:
                        import signal
                        try:
                            os.kill(pid, signal.SIGTERM)
                        except OSError:
                            pass
                    os.remove(pid_file)
                    print(json.dumps({"status": "stopped", "pid": pid}, indent=2))
                except Exception as e:
                    print(json.dumps({"status": "error", "error": str(e)}, indent=2))
            else:
                print(json.dumps({"status": "not_running"}, indent=2))
            sys.exit(0)

        elif args.action == "start":
            srv = SquadOfficeServer(port=args.port)
            url = srv.start(open_browser_tab=not args.no_browser)
            if getattr(args, "json", False):
                print(json.dumps({"status": "online", "url": url, "port": srv.port, "token": srv.session_token}, indent=2))
            else:
                print("=================================================================")
                print(f"🚀 VicnovaLabs Squad Virtual Office is LIVE at:")
                print(f"👉 {url}")
                print("=================================================================")
                print("Press Ctrl+C to terminate the office server.")
            
            try:
                import time
                while srv.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                srv.stop()
                print("\nVirtual Squad Office stopped.")
                sys.exit(0)


if __name__ == "__main__":
    main()
