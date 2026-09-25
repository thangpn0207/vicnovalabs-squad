# 🏛️ VicnovaLabs Squad Architecture & The 4 Pillars

> **Target Version**: `v2.1.0`  
> **Architecture Pattern**: Governed Multi-Agent Execution Platform with Strict Separation of Concerns.

---

## 1. The 6 Specialized Squad Roles

| Agent | Specialized Domain | Core Competencies | Key Tools & Deliverables |
|---|---|---|---|
| **`squad-ba`** | Business Analysis & Architecture | Requirements Elicitation, User Stories, Gherkin Criteria, Risk Modeling | `ArchitectureDecision` (ADR), `before-you-build`, `writing-plans` |
| **`squad-design`** | UI/UX & Layout Engineering | Apple HIG, Fluid Motion, Tactile Ergonomics, Design Systems | 3-Option Interactive Mockups, `ui-ux-pro-max`, `ui-audit` |
| **`squad-dev`** | Full-Stack Software Engineering | Clean Code, Composition Patterns, Modular Architecture, Supabase | Filesystem writes, unit tests, `HandoffManifest` (Coverage >= 85%) |
| **`squad-debug`** | Systems Debugging & SRE | Root Cause Analysis, Empirical Hypothesis Testing, Surgical Patches | `rank-hypotheses`, `systematic-debugging`, minimal diff patches |
| **`squad-qa`** | Adversarial Acceptance & SDET | Bug Hunting Mindset, POAI Verification, Torture Fuzzing | Standalone test runners, ADB/Playwright execution, `SignoffReceipt` |
| **`squad-marketing`** | Growth Marketing & Copywriting | Conversion Optimization (CRO), Value Proposition, Anti-Slop Copy | Landing page copy, SEO architecture, `avoid-ai-writing` |

---

## 2. Common Agent Contract & Governance

All 6 squad agents adhere to the **Common Agent Contract**:

1. **Zero Code-Offloading**:
   Agents equipped with write tools (`squad-dev`, `squad-debug`, `squad-design`) MUST write all files directly to disk and execute self-tests themselves. Outputting raw code in conversation with instructions to *"apply this code"* is strictly prohibited.
2. **Deterministic Requirement Traceability (`REQ-XXX`)**:
   - `squad-ba` assigns formal IDs (e.g. `REQ-001`, `REQ-002`) in requirements specs.
   - `squad-dev` links touched code to these IDs in `HandoffManifest.requirement_ids`.
   - `squad-qa` verifies each ID independently in `SignoffReceipt.requirement_ids`.
3. **Boundaries & Scope Control**:
   - `squad-dev` and `squad-design` NEVER self-grant `[x] DONE` status. They set modules to `[-] READY_FOR_QA`.
   - `squad-qa` NEVER edits source code. It only produces `SignoffReceipt` (DONE) or `DefectTicket` (REJECT).
   - Only `squad-debug` or `squad-dev` can apply fixes upon receiving a `DefectTicket`.

---

## 3. The 4 Architecture Pillars

```
                               ┌────────────────────────────────┐
                               │   VICNOVALABS SQUAD ENGINE     │
                               └───────────────┬────────────────┘
                                               │
             ┌───────────────────┬─────────────┴─────┬───────────────────┐
             ▼                   ▼                   ▼                   ▼
     ┌───────────────┐   ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
     │   PILLAR 1    │   │   PILLAR 2    │   │   PILLAR 3    │   │   PILLAR 4    │
     │  5-Tier Memory│   │   Crawl4AI    │   │   Stagehand   │   │  Superpowers  │
     │  & Compactor  │   │ Micro-Crawler │   │ UI Primitives │   │ Safe Worktrees│
     └───────────────┘   └───────────────┘   └───────────────┘   └───────────────┘
```

---

### Pillar 1: OpenClaw 5-Tier Memory & Compactor

The Squad Engine manages persistent project context using a structured 5-tier classification system:

1. **`[VERIFIED]`**: Lessons backed by empirical tests, oracle verdicts, or passing CI runs.
2. **`[DECISION]`**: User-approved Architecture Decision Records (ADRs) or deliberate design choices.
3. **`[INFERRED]`**: Hypotheses or contextual insights deduced by agents during execution.
4. **`[HISTORICAL]`**: Legacy project context preserved for auditability.
5. **`[SUPERSEDED]`**: Outdated decisions marked obsolete via `squad memory supersede <topic>`. Excluded from active context to prevent prompt confusion.

**Context Compactor**: Truncates runaway terminal output and large stacktraces, preserving head and tail lines with a bounded summary.

---

### Pillar 2: Crawl4AI Clean Micro-Crawler

Standard web scrapers dump megabytes of HTML, JavaScript bundles, navigation links, and tracking scripts into the LLM prompt.  
`squad crawl` solves this by:
- Stripping `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, and ads.
- Extracting main semantic content into clean, token-dense Markdown.
- Enforcing strict token budgets (`--max-tokens 1500`).
- **Security Hardening**: Enforces an SSRF blacklist blocking private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.1`), and cloud metadata IP (`169.254.169.254`).

---

### Pillar 3: Stagehand-Inspired Self-Healing UI Primitives

Located in `skills/squad_qa/test_primitives.js`, these primitives make automated browser tests resilient against brittle DOM mutations:
- **`smartClick(page, descriptor)`**: Dynamically probes multiple selector layers: `data-testid` $\rightarrow$ `role` $\rightarrow$ `aria-label` $\rightarrow$ visible text $\rightarrow$ CSS selector.
- **`smartFill(page, descriptor, value)`**: Simulates realistic human typing, dispatches input/change events, and handles custom framework hydration states.
- **`tortureFuzzInput(page, descriptor)`**: Injects fuzzing vectors automatically to stress test validation handlers.

---

### Pillar 4: Superpowers Safe Git Worktrees

Enables true parallel subagent execution without git index corruption or dirty working directory collisions:
- **Isolation**: Each worker runs in an independent `.worktrees/<task_slug>` directory with branch `squad/<task_slug>`.
- **Pre-Merge Dirty Check**: Rejects merge if the main repo working directory has uncommitted modifications (ignoring `.worktrees`).
- **Test-Before-Merge Policy**: Executes `--test-command` inside the worktree before accepting the merge.
- **Atomic Merge Abort**: If merge conflicts occur, runs `git merge --abort` immediately to leave the working branch clean.
