# Execution Protocol (Loaded On-Demand Only)

Loaded ONLY when:
1. Tier 1 manual invocation occurs (`/squad <role>`, `/squad full`), OR
2. Tier 2 auto-escalation is confirmed by the user or configured via `mode: auto`.

## 1. 3-Tier Execution Architecture
- **Tier 0 (Passive Scanner)**: Runs on every diff, ~0 cost. Fast-paths safe changes (*.css, *.md, <=50 lines). Flags sensitive domains (auth/security, db/migrations, ci_cd, dependency, public_api_surface).
- **Tier 1 (Manual On-Demand)**: Default mode. Single-agent execution (`/squad <role>`). No forced downstream pipeline or chained handoffs.
- **Tier 2 (Auto-Escalation)**: Triggered only on high blast-radius signals. Emits 1-line soft suggestion. Full pipeline executes only on explicit opt-in (`/squad full` or user confirmation) or `mode: auto`.

## 2. Typed Handoff Schemas
- **HandoffManifest (Dev -> QA)**:
  - `feature_name`, `target_platform`, `modified_files`, `touched_screens_or_routes`, `test_endpoints_or_selectors`, `deterministic_ingress`, `verification_command`, `self_test_result`, `coverage_report` (Line >= 85%, Branch >= 80%), `requirement_ids`.
- **DefectTicket (QA -> Dev/Debug)**:
  - `ticket_id`, `target_screen`, `selector`, `repro_steps`, `observed_behavior`, `expected_behavior`, `severity`, `logcat_error_snippet`, `retry_count`.
- **SignoffReceipt (QA -> Orchestrator)**:
  - `status` ("PASS" | "REJECT"), `result_status`, `verified_features`, `coverage_achieved`, `poai_verified` (True), `defect_count`, `requirement_ids`.
- **AdversarialCritique (Debug -> Gate)**:
  - `target_domain`, `skeptic_agent`, `unstated_assumptions`, `race_conditions`, `attack_vectors`, `verdict` ("APPROVE" | "CONCERN" | "BLOCK").

## 3. Scope-Adaptive Testing & Torture Dimensions
- **UI/Copy Diff**: Visual fidelity inspection, accessibility check, smoke render. Zero SQLi or fuzzing torture.
- **Logic Diff (Non-sensitive)**: Targeted tests on modified module only (`test/` runner), state mutation check.
- **Sensitive Path / Security Diff**:
  - Dimension 1: Extreme boundary fuzzing, malformed payloads.
  - Dimension 2: Concurrent race conditions, network flaps, async interleaving.
  - Dimension 3: Security & injection probing (SQLi, IDOR, privilege escalation).

## 4. Subagent Execution Invariants
- **Zero Code-Offloading**: Subagents write changes directly to disk; never request parent agent to apply diffs.
- **QA Black-Box Policy**: squad-qa is forbidden from modifying or reading source code files (`lib/**/*`, `src/**/*`). Tests must run via standalone runner scripts in `test/`.
- **Execution Receipt**: Full execution logs saved to `/tmp/squad_runs/<run_id>.log`. Chat context receives bounded summary <= 5 lines.
