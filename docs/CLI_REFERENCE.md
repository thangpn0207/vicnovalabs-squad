# 📖 VicnovaLabs Squad — Complete CLI Reference Manual

> **Version**: `v2.1.0` (Governed Multi-Agent Execution Platform & Evidence-Driven QA)  
> **Executable**: `squad` (or `python3 jev_triage.py`)

This document is the authoritative reference for all commands, parameters, options, environment variables, and return codes in the VicnovaLabs Squad Engine.

---

## Table of Contents
1. [Global Options & Environment Variables](#1-global-options--environment-variables)
2. [Primary AI Gateway (Single Ingress)](#2-primary-ai-gateway-single-ingress)
   - [`squad dispatch`](#squad-dispatch)
   - [`squad mode`](#squad-mode)
3. [Evidence-Driven QA (EDQA) & Test Harness](#3-evidence-driven-qa-edqa--test-harness)
   - [`squad preflight`](#squad-preflight)
   - [`squad test-run`](#squad-test-run)
   - [`squad validate-evidence`](#squad-validate-evidence)
   - [`squad validate-handoff`](#squad-validate-handoff)
   - [`squad get-schema`](#squad-get-schema)
4. [The 4 Architecture Pillars](#4-the-4-architecture-pillars)
   - [Pillar 1: `squad memory`](#pillar-1-squad-memory)
   - [Pillar 2: `squad crawl`](#pillar-2-squad-crawl)
   - [Pillar 3: Stagehand UI Primitives](#pillar-3-stagehand-ui-primitives)
   - [Pillar 4: `squad worktree`](#pillar-4-squad-worktree)
5. [Orchestration, Task Plans & Progress](#5-orchestration-task-plans--progress)
   - [`squad task-plan`](#squad-task-plan)
   - [`squad orchestrate`](#squad-orchestrate)
   - [`squad progress`](#squad-progress)
6. [Diagnostics & System Operations](#6-diagnostics--system-operations)
   - [`squad status`](#squad-status)
   - [`squad device-audit`](#squad-device-audit)
   - [`squad audit-skills`](#squad-audit-skills)
   - [`squad config`](#squad-config)
   - [`squad list-agents`](#squad-list-agents)
   - [`squad get-agent-def`](#squad-get-agent-def)
   - [`squad sync-workspace`](#squad-sync-workspace)
   - [`squad stack`](#squad-stack)
   - [`squad ui-audit`](#squad-ui-audit)
   - [`squad rank-hypotheses`](#squad-rank-hypotheses)
   - [`squad subagent-watchdog`](#squad-subagent-watchdog)

---

## 1. Global Options & Environment Variables

### Environment Variables
- `SQUAD_DISPATCH_MODE`: Default dispatch mode (`suggest`, `smart`, `auto`, `inline`). Default is `suggest`.
- `SQUAD_DEV_DEVICE`: Target device serial for ADB testing (e.g. `emulator-5554`).
- `SQUAD_QA_SCREENSHOT`: Enable/disable visual screenshot archiving (`true` / `false`). Default is `true`.
- `TYPESAFE_API_KEY`: Optional API key for remote semantic triage. When unset, offline regex heuristics run at **0 token cost**.
- `SQUAD_LOG_LEVEL`: Log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`).

---

## 2. Primary AI Gateway (Single Ingress)

### `squad dispatch`
Triages intent, analyzes complexity, curates phase-specific skills, verifies hardware, and outputs the execution directive in a single atomic call.

```bash
squad dispatch "<prompt>" [options]
```

**Options**:
- `--mode`, `-m`: Override dispatch mode (`suggest`, `smart`, `auto`, `inline`).
- `--platform`, `-p`: Target platform (`web` or `mobile`, default: `web`).
- `--domain`, `-d`: Domain context tag (e.g. `auth`, `payment`, `ui`).
- `--workspace`, `-w`: Target workspace root (defaults to current directory).
- `--json`: Emit machine-readable pure JSON response.

**Examples**:
```bash
# Suggestion mode (renders Markdown suggestion card, executes inline by default)
squad dispatch "thêm nút copy vào giao diện" --mode suggest

# Smart mode (auto-dispatches subagent if complexity >= 4, otherwise executes inline)
squad dispatch "refactor architecture to event-driven microservices" --mode smart

# Mobile task with auto ADB hardware triage
squad dispatch "test luồng thanh toán QR code trên điện thoại" --platform mobile

# Pure JSON output for IDE automation hooks
squad dispatch "fix bug null pointer in AuthService" --json
```

---

### `squad mode`
Inspects or changes the squad execution mode with project or session scoping.

```bash
squad mode [target_mode] [options]
```

**Positional Argument**:
- `target_mode`: Target mode (`suggest`, `smart`, `auto`, `inline`, or `status`). Omit to view status.

**Options**:
- `--scope`, `-s`: `project` (persists to `.squad_mode` and `.env`) or `session` (memory cache only).
- `--workspace`, `-w`: Workspace path.
- `--session`: Active session ID.
- `--json`: Output mode information in JSON format.

**Examples**:
```bash
# Check effective mode
squad mode

# Set project-level mode to smart
squad mode smart --scope project

# Set session-only mode to auto
squad mode auto --scope session
```

---

## 3. Evidence-Driven QA (EDQA) & Test Harness

### `squad preflight`
Verifies physical or virtual ADB hardware readiness before running mobile acceptance tests. Prevents testing on broken or low-storage emulators.

```bash
squad preflight [serial] [options]
```

**Options**:
- `serial`: ADB serial number (default: `emulator-5554`).
- `--package`, `-p`: Android package ID to check (e.g. `com.example.app`).
- `--min-storage`: Minimum free disk space in MB required on device (default: `500`).
- `--json`: Output pure JSON report.

**Checks Performed**:
1. Device online state & authorization.
2. Free internal storage on `/data` (`df -k /data`).
3. Window manager display dimensions (`wm size`).
4. Battery status & charging state (`dumpsys battery`).
5. Target package installation status (`pm path <package>`).

**Examples**:
```bash
squad preflight emulator-5554
squad preflight emulator-5554 --package com.example.shop --min-storage 300
```

---

### `squad test-run`
Generates and executes a standalone, hermetic test runner script on the host CPU in milliseconds. Enforces the **Batch Test Runner Script Pattern** (eliminating multi-turn interactive ADB token loops).

```bash
squad test-run [options]
```

**Options**:
- `--stack`: Stack profile (`auto`, `flutter`, `web_frontend`, `react_native`, `node_backend`, `python`, `go`, `rust`, `android_native`, `ios_native`, `generic`).
- `--suite`: Journey name (`app_launch`, `auth_flow`, `checkout`, etc.).
- `--device`: Target ADB device serial for mobile (default: `emulator-5554`).
- `--package`: Target mobile package name.
- `--url`: Target Web URL for Playwright tests (default: `http://localhost:3000`).
- `--evidence-dir`: Output directory where screenshots and logs are persisted.
- `--dry-run`: Generate script content to stdout without executing.

**Example**:
```bash
# Web frontend run
squad test-run --stack web_frontend --url http://localhost:5173 --evidence-dir /tmp/ev_web

# Mobile Flutter run
squad test-run --stack flutter --device emulator-5554 --package com.example.app --evidence-dir /tmp/ev_mobile
```

---

### `squad validate-evidence`
The External Anti-Fraud Oracle. Validates the test evidence directory against strict criteria, preventing false-positive PASS reports.

```bash
squad validate-evidence <evidence_dir> [options]
```

**Options**:
- `evidence_dir`: Directory containing screenshots and logs.
- `--stack`: Stack profile for stack-specific error regexes.
- `--max-age`: Maximum allowable evidence file age in seconds (default: `300`).
- `--json`: Pure JSON output.

**Anti-Deception Rules Enforced**:
1. **Timestamp Freshness**: All evidence files must have been generated recently (not recycled).
2. **Crash/Exception Scans**: Multiline regexes scan logs for unhandled crashes, ANRs, panics, and tracebacks.
3. **3-Strategy Screenshot Mutation**: Pre/Post screenshots are evaluated via perceptual diff, size delta, and SHA256 hash. Identical screenshots cause rejection.
4. **Non-Zero Exit Code**: If the runner script failed or threw an assertion error, the evidence bundle is invalidated.

---

### `squad validate-handoff`
Validates typed JSON hand-off payloads against strict schema contracts.

```bash
squad validate-handoff <schema_type> <payload> [options]
```

**Arguments**:
- `schema_type`: `manifest` (Dev $\rightarrow$ QA), `defect` (QA $\rightarrow$ Dev), `decision` (BA $\rightarrow$ Dev), or `acceptance` (QA Signoff).
- `payload`: Path to `.json` file or raw JSON string.

**Options**:
- `--strict-evidence`: Enforces that runner exit code equals 0 and evidence directory is valid.
- `--strict-traceability`: Enforces that `requirement_ids` is present and non-empty.
- `--exit-code`: Process exit code of runner.
- `--evidence-dir`: Evidence directory path.

**Example**:
```bash
squad validate-handoff manifest ./handoff.json --strict-traceability
squad validate-handoff acceptance ./receipt.json --strict-evidence --exit-code 0 --evidence-dir /tmp/ev
```

---

### `squad get-schema`
Outputs the exact JSON schema definition for typed handoffs.

```bash
squad get-schema [manifest|defect|decision|acceptance|all]
```

---

## 4. The 4 Architecture Pillars

### Pillar 1: `squad memory`
Manages the OpenClaw 5-Tier Persistent Memory architecture and context compactor.

```bash
squad memory <action> [text] [options]
```

**Actions**:
- `status`: Show token usage across SOUL, MEMORY, and WORKING tiers.
- `record`: Append a permanent insight to `MEMORY.md`.
- `supersede`: Mark older insights matching a topic as `[SUPERSEDED]`.
- `compact`: Compress long terminal logs or stacktraces into bounded summaries.
- `working`: View the current volatile working scratchpad.

**Options**:
- `--topic`: Category label for the insight.
- `--tier`: Trust tier: `verified`, `decision`, `inferred`, `historical`, or `superseded` (default: `inferred`).
- `--reason`: Rationale when superseding older decisions.

**Examples**:
```bash
# Record verified pattern
squad memory record "Always wrap Playwright page actions in try...finally" --topic BrowserAutomation --tier verified

# Supersede deprecated architecture decision
squad memory supersede "StateManagement" --reason "Migrated from Redux to Zustand in ADR-005"

# Compact giant terminal output
cat build.log | squad memory compact
```

---

### Pillar 2: `squad crawl`
Crawl4AI clean micro-crawler. Fetches documentation or web pages and converts them to token-dense Markdown while stripping noise, scripts, navigation bars, and cookie banners.

```bash
squad crawl <url> [options]
```

**Options**:
- `--max-tokens`, `-t`: Maximum token budget (default: `1500`).
- `--output`, `-o`: Save markdown output to target file path.
- `--json`: Output JSON with metadata, token estimate, and stripped content.

**Security**: Automatically blocks private IP ranges, loopback (`127.0.0.1`), and AWS/GCP cloud metadata services (`169.254.169.254`).

**Examples**:
```bash
squad crawl "https://pub.dev/packages/supabase_flutter" --max-tokens 1200 -o docs/supabase.md
```

---

### Pillar 3: Stagehand UI Primitives
Self-healing, resilient automation primitives located in `skills/squad_qa/test_primitives.js`. They automatically fallback across multiple selector strategies:
- `smartClick(page, descriptor)`: Tries `[data-testid]`, `role`, `aria-label`, text content, and CSS selector.
- `smartFill(page, descriptor, value)`: Safely clears, focuses, fills, and fires blur events.
- `tortureFuzzInput(page, descriptor)`: Injects boundary fuzzed strings (SQLi probes, emojis, overflows, XSS payloads).

---

### Pillar 4: `squad worktree`
Manages Superpowers Git Worktrees for parallel subagent execution. Eliminates cross-agent git race conditions and merge conflicts.

```bash
squad worktree <action> [slug] [options]
```

**Actions**:
- `create <slug>`: Creates branch `squad/<slug>` in isolated folder `.worktrees/<slug>`.
- `list`: Lists active squad worktrees.
- `merge <slug>`: Safely merges `squad/<slug>` back into the current branch and removes the worktree.
- `remove <slug>`: Discards a worktree.

**Options**:
- `--test-command`, `-t`: Command that MUST pass before merge is accepted (test-before-merge policy).
- `--repo`, `-r`: Repository root directory.

**Safety Protocols**:
1. Checks that main working tree is clean before merging (ignoring `.worktrees`).
2. Runs `--test-command` in worktree directory before merging.
3. Automatically executes `git merge --abort` if merge conflicts occur.

**Examples**:
```bash
squad worktree create feat-payment
squad worktree merge feat-payment --test-command "pytest tests/test_payment.py"
```

---

## 5. Orchestration, Task Plans & Progress

### `squad task-plan`
Manages hierarchical subtask decomposition and fan-out execution tracking.

```bash
squad task-plan <init|status|update|reconcile|decompose|prune> [arguments] [options]
```

**Examples**:
```bash
# Initialize a plan with subtasks
squad task-plan init "Checkout System" "Cart Validation" "Stripe Gateway" "Receipt Email"

# Check subtask statuses
squad task-plan status

# Update a subtask
squad task-plan update --plan .agents/plans/TASK_PLAN_01.md --subtask ST-01 --status READY_FOR_QA --note "Unit tests pass"

# Reconcile completed subtasks into root PROJECT_PROGRESS.md
squad task-plan reconcile

# Prune old plans to maintain token efficiency
squad task-plan prune --keep 5
```

---

### `squad orchestrate`
Autonomous closed-loop squad orchestration pipeline. Connects Dev handoffs, QA acceptance runs, and Defect Ticket loopbacks.

```bash
squad orchestrate [options]
```

**Options**:
- `--manifest <file>`: Process a Dev `HandoffManifest` (transitions module to `READY_FOR_QA` and triggers QA).
- `--receipt <file>`: Process a QA `SignoffReceipt` (verifies POAI and promotes module to `[x] DONE`).
- `--defect <file>`: Process a Defect Ticket (triggers Dev bugfix loop).
- `--prompt <text>`: Run autonomous pipeline from initial user prompt.

---

### `squad progress`
Inspects and manages `PROJECT_PROGRESS.md` status, percent completion, and defect counters. Protected with advisory file locking (`fcntl.flock`).

```bash
squad progress status
squad progress init "My Project" "Auth Module" "Payment Gateway" "Reporting"
```

---

## 6. Diagnostics & System Operations

| Command | Description |
|---|---|
| `squad status` | Displays squad home, active IDE, dispatch mode, API key status, and connected devices. |
| `squad device-audit` | Audits connected ADB emulators vs physical hardware devices. |
| `squad audit-skills` | Compares installed IDE skills against the recommended modular squad catalog. |
| `squad config` | Views or sets engine configuration (e.g. `squad config qa-screenshot off`). |
| `squad list-agents` | Lists the 6 specialized squad agents and their system descriptions. |
| `squad get-agent-def <role>` | Outputs the full system prompt and tool definitions for dynamic agent registration. |
| `squad sync-workspace` | Syncs agent prompt templates and skills directly into the active workspace. |
| `squad stack` | Detects technology stack, test runners, and platform tooling in the workspace. |
| `squad ui-audit <mock> <code>` | Evaluates visual/structural fidelity between reference HTML mockup and code. |
| `squad rank-hypotheses <trace> <h1...>` | Ranks debugging hypotheses using empirical evidence scores. |
| `squad subagent-watchdog <json>` | Monitors active subagents, detecting hangs, runaway loops, and 429 quota exhaustion. |

---
*Generated for VicnovaLabs Squad v2.1.0 Architecture Reference.*
