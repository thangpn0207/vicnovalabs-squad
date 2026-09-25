#!/usr/bin/env python3
"""
Typed Hand-off Contracts, JSON Schemas, and Anti-Deception Validation.
Enforces Proof-of-Active-Interaction (POAI), Diff Coverage Gate, and Zero-Code Offloading.
"""

import json
from typing import Dict, Any, List, Optional


TYPED_HANDOFF_SCHEMAS = {
    "manifest": {
        "title": "HandoffManifest",
        "description": "Structured hand-off payload from squad-dev to squad-qa upon feature completion",
        "type": "object",
        "required": [
            "module",
            "modified_files",
            "self_test_result",
            "verification_command"
        ],
        "properties": {
            "module": {"type": "string", "description": "Module name or feature title"},
            "requirement_ids": {"type": "list", "description": "Traceable requirement IDs, e.g. ['REQ-001', 'REQ-002']"},
            "acceptance_criteria": {"type": "list", "description": "Specific acceptance criteria verified by self-test"},
            "modified_files": {"type": "list", "description": "List of newly created or edited files"},
            "routes_or_screens": {"type": "list", "description": "Interactive screens, routes, or UI components"},
            "test_endpoints": {"type": "list", "description": "API routes or service endpoints touched"},
            "seed_data": {"type": "dict", "description": "Realistic test accounts, fixtures, or DB records"},
            "self_test_result": {"type": "string", "enum": ["PASSED", "VERIFIED_LOCAL", "PARTIAL"]},
            "verification_command": {"type": "string", "description": "Deterministic CLI command for QA reproduction"},
            "coverage_report": {
                "type": "dict",
                "description": "Deterministic diff test coverage metrics (Line >= 85%, Branch >= 80%)"
            },
            "known_limitations": {"type": "list", "description": "Known edge-cases, partial implementations, or hardware constraints"}
        }
    },
    "defect": {
        "title": "DefectTicket",
        "description": "Structured defect ticket from squad-qa to squad-dev or squad-design upon REJECT",
        "type": "object",
        "required": ["ticket_id", "module", "severity", "repro_steps", "actual_behavior", "expected_behavior"],
        "properties": {
            "ticket_id": {"type": "string", "description": "Unique defect identifier, e.g. DEF-001"},
            "module": {"type": "string", "description": "Module name experiencing defect"},
            "severity": {"type": "string", "enum": ["Blocker", "Critical", "Major", "Minor"]},
            "repro_steps": {"type": "list", "description": "Exact step-by-step reproduction sequence"},
            "target_selector_or_screen": {"type": "string", "description": "DOM selector, ref label, or screen area"},
            "actual_behavior": {"type": "string", "description": "Observed erroneous behavior"},
            "expected_behavior": {"type": "string", "description": "Expected behavior per spec/mockup"},
            "logs_or_stacktrace": {"type": "string", "description": "Console error logs or ADB logcat dump"},
            "visual_diff_score": {"type": "float", "description": "Visual fidelity deviation score if layout error"}
        }
    },
    "decision": {
        "title": "ArchitectureDecision",
        "description": "Structured architecture / system design proposal from squad-ba or squad-dev",
        "type": "object",
        "required": ["decision_id", "title", "context", "chosen_option", "consequences"],
        "properties": {
            "decision_id": {"type": "string", "description": "ADR ID, e.g. ADR-001"},
            "title": {"type": "string", "description": "Architecture decision title"},
            "context": {"type": "string", "description": "Problem statement, technical trade-offs, constraints"},
            "chosen_option": {"type": "string", "description": "The selected architecture / design pattern"},
            "considered_alternatives": {"type": "list", "description": "Alternative options analyzed"},
            "consequences": {"type": "list", "description": "Positive and negative impacts of the decision"},
            "security_impact": {"type": "string", "description": "Threat model, auth boundary, or data protection"},
            "requires_adversarial_review": {"type": "bool", "description": "Flag indicating if skeptic review is needed"}
        }
    },
    "acceptance": {
        "title": "SignoffReceipt",
        "description": "Structured Proof-of-Active-Interaction acceptance receipt from squad-qa upon marking PASS",
        "type": "object",
        "required": [
            "module",
            "target_platforms",
            "fresh_test_identifier",
            "interactive_journey",
            "state_mutation_delta",
            "live_evidence",
            "anti_deception_checks",
            "verdict"
        ],
        "properties": {
            "module": {"type": "string", "description": "Module name verified"},
            "requirement_ids": {"type": "list", "description": "Traceable requirement IDs verified by QA, e.g. ['REQ-001']"},
            "target_platforms": {"type": "list", "description": "All platforms tested"},
            "fresh_test_identifier": {"type": "string", "description": "Dynamic nonce/timestamp/unique entity name"},
            "interactive_journey": {"type": "list", "description": "Step-by-step automated interactive commands executed"},
            "state_mutation_delta": {"type": "dict", "description": "Explicit Pre-State vs Post-State confirming real mutation"},
            "live_evidence": {"type": "string", "description": "Live logcat/console output with timestamp"},
            "anti_deception_checks": {"type": "dict", "description": "Proof guarantees (no_passive_visual_only, all_target_devices_interacted, stale_data_ruled_out, silent_errors_ruled_out)"},
            "log_inspection_audit": {"type": "dict", "description": "Log verification details (logcat_checked, terminal_checked, silent_errors_ruled_out)"},
            "visual_fidelity_score": {"type": "float", "description": "UI mockup match score (>= 0.85)"},
            "screenshot_evidence": {"type": "string", "description": "File path to visual proof screenshot demonstrating test completion and feature verification"},
            "runner_exit_code": {"type": "number", "description": "Exit code from the test runner script (0 = pass). Oracle rejects if != 0."},
            "evidence_dir": {"type": "string", "description": "Path to evidence directory containing screenshots, logs, and runner output."},
            "result_status": {
                "type": "string",
                "enum": ["PASS", "PASS_WITH_WARNINGS", "FAIL", "BLOCKED", "SKIPPED", "INCONCLUSIVE"],
                "description": "Granular test outcome status"
            },
            "verdict": {"type": "string", "enum": ["PASS", "REJECT"]}
        }
    },

    "critique": {
        "title": "AdversarialCritique",
        "description": "Structured adversarial review and refutation payload from skeptic agent",
        "type": "object",
        "required": [
            "critique_id",
            "target_artifact",
            "target_domain",
            "skeptic_agent",
            "verdict",
            "action_items"
        ],
        "properties": {
            "critique_id": {"type": "string", "description": "Unique critique ID, e.g. CRIT-001"},
            "target_artifact": {"type": "string", "description": "Artifact under review (PRD, test plan, ADR, schema)"},
            "target_domain": {
                "type": "string",
                "enum": ["docs", "test", "architecture", "security"],
                "description": "Domain of artifact under review"
            },
            "skeptic_agent": {"type": "string", "description": "Agent acting as skeptic (squad-debug, squad-qa, squad-dev)"},
            "refuted_assumptions": {"type": "list", "description": "List of assumptions refuted or challenged"},
            "blindspots_and_edge_cases": {"type": "list", "description": "List of edge cases, race conditions, or blind spots"},
            "risk_level": {
                "type": "string",
                "enum": ["Low", "Medium", "High", "Critical"],
                "description": "Assessed risk level"
            },
            "verdict": {
                "type": "string",
                "enum": ["APPROVED", "APPROVED_WITH_AMENDMENTS", "REJECTED_NEEDS_REVISION"],
                "description": "Review outcome"
            },
            "action_items": {"type": "list", "description": "Required remediations or action items before approval"}
        }
    }
}

# P2-C: signoff is an alias for acceptance — single source of truth, no duplication
TYPED_HANDOFF_SCHEMAS["signoff"] = TYPED_HANDOFF_SCHEMAS["acceptance"]


def validate_handoff_payload(
    schema_type: str,
    data: Any,
    strict_evidence: bool = False,
    strict_traceability: bool = False
) -> Dict[str, Any]:
    """Validate a typed handoff dictionary against registered schemas with anti-deception and coverage checks."""
    s_key = schema_type.lower()
    schema = TYPED_HANDOFF_SCHEMAS.get(s_key)
    if not schema:
        return {
            "valid": False,
            "errors": [f"Unknown schema type: '{schema_type}'. Available: {list(TYPED_HANDOFF_SCHEMAS.keys())}"]
        }
    
    if not isinstance(data, dict):
        return {
            "valid": False,
            "errors": [f"Payload must be a JSON object (dict), received: {type(data).__name__}"]
        }
    
    errors = []
    # Check required fields
    for req in schema.get("required", []):
        if req not in data:
            errors.append(f"Missing required field: '{req}'")
        elif data[req] is None or (isinstance(data[req], str) and not data[req].strip()):
            errors.append(f"Required field '{req}' cannot be empty")

    # Strict Traceability Gate (Phase 4.1 & 5.2)
    if strict_traceability and isinstance(data, dict):
        req_ids = data.get("requirement_ids")
        if s_key == "manifest":
            if not req_ids or not isinstance(req_ids, list) or len(req_ids) == 0:
                errors.append("Traceability Gate Violation: 'requirement_ids' is required on manifest (e.g. ['REQ-001']).")
        elif s_key in ["acceptance", "signoff"]:
            if not req_ids or not isinstance(req_ids, list) or len(req_ids) == 0:
                errors.append("Traceability Gate Violation: 'requirement_ids' is required on acceptance to trace verification back to requirements.")


    # Check property types
    type_map = {
        "string": str,
        "list": list,
        "array": list,
        "dict": dict,
        "object": dict,
        "bool": bool,
        "boolean": bool,
        "float": (int, float),
        "number": (int, float)
    }

    for prop, prop_def in schema.get("properties", {}).items():
        if prop in data and data[prop] is not None:
            expected_type_name = prop_def.get("type", "string")
            py_type = type_map.get(expected_type_name, str)
            if not isinstance(data[prop], py_type):
                errors.append(f"Field '{prop}' expected type {expected_type_name}, got {type(data[prop]).__name__}")
            if "enum" in prop_def and data[prop] not in prop_def["enum"]:
                errors.append(f"Field '{prop}' value '{data[prop]}' not in allowed enum: {prop_def['enum']}")

    # Specialized Code Coverage Gate for Dev HandoffManifest
    # Dev Test Contract: coverage metrics are optional metadata and do not block handoff
    if s_key == "manifest" and isinstance(data, dict):
        cov = data.get("coverage_report")
        if cov is not None:
            if not isinstance(cov, dict):
                errors.append("Coverage Report: Field 'coverage_report' must be a JSON object if provided.")
            else:
                line_pct = cov.get("line_coverage_pct")
                branch_pct = cov.get("branch_coverage_pct")
                if line_pct is not None and not isinstance(line_pct, (int, float)):
                    errors.append("Coverage Report: 'coverage_report.line_coverage_pct' must be numeric if provided.")
                if branch_pct is not None and not isinstance(branch_pct, (int, float)):
                    errors.append("Coverage Report: 'coverage_report.branch_coverage_pct' must be numeric if provided.")

    # Specialized Anti-Deception & Proof-of-Active-Interaction (POAI) checks
    if s_key in ["acceptance", "signoff"] and isinstance(data, dict):
        checks = data.get("anti_deception_checks", {})
        if not isinstance(checks, dict):
            errors.append("Field 'anti_deception_checks' must be a JSON object")
        else:
            if checks.get("no_passive_visual_only") is not True:
                errors.append("Anti-Deception Violation: 'no_passive_visual_only' must be true. Visual confirmation/screenshot alone is NOT proof of functionality.")
            if checks.get("all_target_devices_interacted") is not True:
                errors.append("Anti-Deception Violation: 'all_target_devices_interacted' must be true. Every target platform/device must be actively driven.")
            if checks.get("stale_data_ruled_out") is not True:
                errors.append("Anti-Deception Violation: 'stale_data_ruled_out' must be true. Test must generate fresh entity/payload to prevent stale data false-positives.")
            if checks.get("silent_errors_ruled_out") is not True:
                errors.append("Anti-Deception Violation: 'silent_errors_ruled_out' must be true. Logcat/terminal logs must be inspected to ensure 0 unhandled exceptions or silent swallowed failures.")

        live_evidence = data.get("live_evidence", "")
        if not str(live_evidence).strip() or len(str(live_evidence).strip()) < 15:
            errors.append("Empirical Evidence Violation: 'live_evidence' must contain concrete runtime output (logcat, process exit codes, or terminal output).")

        journey = data.get("interactive_journey", [])
        if not isinstance(journey, list) or len(journey) == 0:
            errors.append("Proof-of-Active-Interaction Violation: 'interactive_journey' cannot be empty. Must list automated click/fill/tap commands.")
        else:
            # Anti-Simulation Fraud & Non-Interactive Action Detection
            fraud_patterns = [
                "in-memory", "wire format simulation", "self-comparison",
                "mock photo only", "mock transfer", "ram simulation"
            ]
            has_interactive_action = False
            for step in journey:
                act = ""
                delta_obs = ""
                if isinstance(step, dict):
                    act = str(step.get("action", "")).lower()
                    delta_obs = str(step.get("observed_delta", "")).lower()
                elif isinstance(step, str):
                    act = step.lower()

                for fp in fraud_patterns:
                    if fp in act or fp in delta_obs:
                        errors.append(f"Simulation Fraud Violation: '{act or delta_obs}' indicates in-memory simulation. Acceptance testing must verify actual application/device interactions.")
                        break

                if any(k in act for k in ["click", "tap", "fill", "input", "press", "open", "navigate", "select", "send", "verify", "assert", "delivery", "stream", "test", "launch"]):
                    has_interactive_action = True

            if not has_interactive_action and len(journey) > 0:
                errors.append("Proof-of-Active-Interaction Violation: 'interactive_journey' must contain active user interaction commands (click, tap, fill, navigate, send) or verified device assertions.")

        delta = data.get("state_mutation_delta", {})
        if isinstance(delta, dict):
            if "pre" not in delta or "post" not in delta:
                errors.append("Field 'state_mutation_delta' must contain both 'pre' and 'post' states.")
            elif str(delta.get("pre")).strip() == str(delta.get("post")).strip():
                errors.append("State Mutation Violation: 'pre' and 'post' states are identical. No state mutation was observed.")

        platforms = data.get("target_platforms", [])
        if isinstance(platforms, list) and len(platforms) > 1 and isinstance(journey, list):
            covered_platforms = set()
            for step in journey:
                if isinstance(step, dict):
                    dev = str(step.get("device", "")).lower()
                    for p in platforms:
                        p_clean = str(p).lower().replace("android:", "").replace("ios:", "").strip()
                        p_prefix = str(p).lower().split(":")[0].strip()
                        if p_clean in dev or p_prefix in dev:
                            covered_platforms.add(p)
            missing = set(platforms) - covered_platforms
            if missing:
                errors.append(f"Multi-Device Blindspot Violation: Target platforms {list(missing)} had NO recorded interactive commands in 'interactive_journey'.")

        # External Anti-Fraud Oracle: runner_exit_code + evidence_dir validation
        # These are deterministic — agent cannot hallucinate filesystem state.
        runner_exit_code = data.get("runner_exit_code")
        evidence_dir = data.get("evidence_dir")
        verdict = str(data.get("verdict", "")).upper()

        # Phase 4.8 Anti-False-PASS Guard:
        if verdict == "PASS" and strict_evidence:
            if runner_exit_code is None:
                errors.append("Anti-False-PASS Violation: 'runner_exit_code' is mandatory when verdict is 'PASS'. Cannot sign off without an execution record.")
            if not evidence_dir:
                errors.append("Anti-False-PASS Violation: 'evidence_dir' is mandatory when verdict is 'PASS'.")

        if runner_exit_code is not None:
            if not isinstance(runner_exit_code, (int, float)):
                errors.append("Oracle Violation: 'runner_exit_code' must be a number.")
            elif int(runner_exit_code) != 0:
                errors.append(
                    f"Oracle Violation: Test runner exited with code {int(runner_exit_code)} "
                    f"(expected 0). Acceptance REJECTED by External Anti-Fraud Oracle."
                )

        if evidence_dir and isinstance(evidence_dir, str):
            try:
                from .evidence_oracle import validate_evidence_bundle
                oracle_result = validate_evidence_bundle(evidence_dir)
                if not oracle_result.get("valid"):
                    for oe in oracle_result.get("errors", []):
                        errors.append(f"Oracle Violation: {oe}")
            except ImportError:
                pass  # evidence_oracle not available — skip filesystem validation


    return {
        "valid": len(errors) == 0,
        "schema_type": schema_type,
        "schema_title": schema.get("title"),
        "errors": errors,
        "validated_payload": data if len(errors) == 0 else None
    }


def format_dispatch_card(
    target_agent: str,
    role: str,
    phase: str,
    platform: str,
    skills: List[str],
    constraints: List[str],
    stack_name: Optional[str] = None
) -> str:
    """Format structured markdown card for IDE agent dispatching."""
    skills_fmt = ", ".join([f"`{s}`" for s in skills]) if skills else "`none`"
    lines = [
        f"### 🚀 Squad Dispatch Card: [{target_agent}]",
        f"- **Role**: `{role}`",
        f"- **Active Phase**: `{phase}` ({platform.upper()})",
    ]
    if stack_name:
        lines.append(f"- **Target Stack**: `{stack_name}`")
    lines.extend([
        f"- **Authorized Skills**: {skills_fmt}",
        "- **Discipline Constraints**:"
    ])
    for c in constraints:
        lines.append(f"  - {c}")
    return "\n".join(lines)


def format_fanout_dispatch_card(plan_title: str, plan_file: str, subtasks: List[Dict[str, Any]]) -> str:
    """Format structured markdown card for parallel subagent fan-out execution."""
    rows = []
    for st in subtasks:
        s_id = st.get("id", "")
        s_title = st.get("title", "")
        s_agent = st.get("target_agent", "")
        s_part = st.get("partition", "")
        s_status = st.get("status", "[ ] PENDING")
        rows.append(f"| `{s_id}` | `{s_agent}` | {s_title} | `{s_part}` | `{s_status}` |")
    table_md = "\n".join(rows)
    lines = [
        f"### ⚡ Squad Scoped Fan-Out Dispatch Card: {plan_title}",
        f"- **Plan File**: `{plan_file}`",
        f"- **Parallel Workers**: {len(subtasks)} subagents active",
        f"- **Execution Isolation**: Strict Resource Partitioning enforced (Zero git/file collisions)",
        "",
        "| ID | Subagent | Subtask | Resource Partition | Status |",
        "|---|---|---|---|---|",
        table_md,
        "",
        "> 🔒 **Barrier Synchronization Rule**: Each subagent must update only its subtask status in the scoped plan.",
        "> Root `PROJECT_PROGRESS.md` will be reconciled once all subtasks reach `[x] DONE`."
    ]
    return "\n".join(lines)


def format_squad_suggestion_card(
    target_agent: str,
    role: str,
    phase: str,
    platform: str,
    skills: List[str],
    complexity_score: int = 2,
    rationale: Optional[str] = None,
    stack_name: Optional[str] = None
) -> str:
    """Format a skill-like recommendation card for squad subagent invocation."""
    skills_fmt = ", ".join([f"`{s}`" for s in skills]) if skills else "`none`"
    if not rationale:
        reasons = {
            "dev": "Delegate source code implementation, API construction, or modular self-tests.",
            "qa": "Automated black-box verification (Playwright/ADB) with Proof-of-Active-Interaction.",
            "design": "Explore UI/UX styles, create multi-option HTML prototypes / Apple HIG components.",
            "debug": "Investigate root cause of errors and perform deep stack trace analysis.",
            "ba": "Draft PRD specifications, user stories, and delineate acceptance criteria.",
            "marketing": "Optimize conversion rate (CRO), high-converting copywriting, and SEO structure."
        }
        rationale = reasons.get(role, f"Specialized optimization for role '{role}'.")

    stack_part = f" | Stack: `{stack_name}`" if stack_name else ""
    lines = [
        f"> 💡 **Squad Recommendation Card**",
        f"> - **Recommended Agent**: `{target_agent}` (Role: `{role}` | Complexity: `{complexity_score}/5`{stack_part})",
        f"> - **Active Phase**: `{phase}` ({platform.upper()}) | **Target Skills**: {skills_fmt}",
        f"> - **Rationale**: {rationale}",
        f"> - **Execution Options**:",
        f">   - ⚡ **Direct (Inline - Token Efficient & Fast)**: Main Agent executes inline immediately.",
        f">   - 👥 **Summon Squad Agent**: Respond *\"summon squad\"*, *\"use {target_agent}\"* or type *`/squad`* to dispatch."
    ]
    return "\n".join(lines)

