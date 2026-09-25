"""
VicnovaLabs Squad Engine
Multi-IDE Autonomous Agent Orchestration Framework
"""

__version__ = "2.3.0"
__author__ = "VicnovaLabs Team"

from .config import SquadConfig, get_config
from .scope_evaluator import evaluate_scope_risk, ScopeRiskAssessment
evaluate_scope_and_risk = evaluate_scope_risk
from .test_harness import compact_execution_log
from .handoffs import (
    TYPED_HANDOFF_SCHEMAS,
    validate_handoff_payload,
    format_dispatch_card,
    format_fanout_dispatch_card
)
from .gate import squad_gate
from .devices import (
    audit_adb_devices,
    is_hardware_constrained,
    is_device_resume_prompt,
    run_adb_preflight
)

from .ui_audit import calculate_ui_fidelity, audit_ui_files, evaluate_ui_fidelity
from .triage import (
    triage_intent,
    calculate_complexity,
    score_task_complexity,
    dispatch_task,
    get_skills_for_phase,
    audit_recommended_skills,
    infer_domain_from_history
)
from .orchestrator import SquadOrchestrator, orchestrate_pipeline
from .task_plan import (
    init_scoped_task_plan,
    parse_scoped_task_plan,
    update_scoped_task_plan,
    reconcile_scoped_task_plan,
    prune_scoped_plans,
    decompose_large_task,
    is_composite_or_large_task,
    is_single_task
)
from .watchdog import audit_subagents_health
from .progress import parse_project_progress, init_project_progress
from .context_guard import check_context_sufficiency, rank_hypotheses
from .agents_registry import get_agent_definition, get_all_agent_definitions, sync_agents_to_workspace
from .client import get_typesafe_client
from .stack_detector import detect_project_stack, StackProfile, STACK_PROFILES
from .crawler import crawl_url_to_markdown, ReadabilityHTMLParser
from .memory import SquadMemory, compact_context_text
from .worktrees import create_task_worktree, list_task_worktrees, remove_task_worktree, merge_task_worktree
from .fix_agent_setting import fix_agent_setting, AgentSettingFixer, format_fix_report_markdown

__all__ = [
    "SquadConfig",
    "get_config",
    "fix_agent_setting",
    "AgentSettingFixer",
    "format_fix_report_markdown",
    "detect_project_stack",
    "StackProfile",
    "STACK_PROFILES",
    "TYPED_HANDOFF_SCHEMAS",
    "validate_handoff_payload",
    "format_dispatch_card",
    "format_fanout_dispatch_card",
    "squad_gate",
    "audit_adb_devices",
    "is_hardware_constrained",
    "is_device_resume_prompt",
    "run_adb_preflight",

    "calculate_ui_fidelity",
    "audit_ui_files",
    "evaluate_ui_fidelity",
    "triage_intent",
    "calculate_complexity",
    "score_task_complexity",
    "dispatch_task",
    "get_skills_for_phase",
    "audit_recommended_skills",
    "infer_domain_from_history",
    "SquadOrchestrator",
    "orchestrate_pipeline",
    "init_scoped_task_plan",
    "parse_scoped_task_plan",
    "update_scoped_task_plan",
    "reconcile_scoped_task_plan",
    "prune_scoped_plans",
    "decompose_large_task",
    "is_composite_or_large_task",
    "is_single_task",
    "audit_subagents_health",
    "parse_project_progress",
    "init_project_progress",
    "check_context_sufficiency",
    "rank_hypotheses",
    "get_agent_definition",
    "get_all_agent_definitions",
    "sync_agents_to_workspace",
    "get_typesafe_client",
    "crawl_url_to_markdown",
    "ReadabilityHTMLParser",
    "SquadMemory",
    "compact_context_text",
    "create_task_worktree",
    "list_task_worktrees",
    "remove_task_worktree",
    "merge_task_worktree",
    "evaluate_scope_risk",
    "evaluate_scope_and_risk",
    "ScopeRiskAssessment",
    "compact_execution_log",
]

