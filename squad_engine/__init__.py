"""
VicnovaLabs Squad Engine
Multi-IDE Autonomous Agent Orchestration Framework
"""

__version__ = "1.0.0"
__author__ = "VicnovaLabs Team"

from .config import SquadConfig, get_config
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
    is_device_resume_prompt
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
    decompose_large_task,
    is_composite_or_large_task,
    is_single_task
)
from .watchdog import audit_subagents_health
from .progress import parse_project_progress, init_project_progress
from .context_guard import check_context_sufficiency, rank_hypotheses
from .agents_registry import get_agent_definition, get_all_agent_definitions, sync_agents_to_workspace
from .client import get_typesafe_client
from .semantic_evaluator import evaluate_task_semantics, get_semantic_cache

__all__ = [
    "SquadConfig",
    "get_config",
    "TYPED_HANDOFF_SCHEMAS",
    "validate_handoff_payload",
    "format_dispatch_card",
    "format_fanout_dispatch_card",
    "squad_gate",
    "audit_adb_devices",
    "is_hardware_constrained",
    "is_device_resume_prompt",
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
]

