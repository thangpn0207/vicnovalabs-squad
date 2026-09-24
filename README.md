# 🚀 VicnovaLabs Squad

> **Multi-IDE Autonomous AI Agent Squad Framework** (Antigravity, Claude Code, Cursor, Codex / OpenAI).

VicnovaLabs Squad coordinates 6 specialized autonomous software engineering agents under strict architectural invariants: **Zero Code-Offloading**, **Proof-of-Active-Interaction (POAI)**, **Anti-Static Deception**, and **Strict Separation of Concerns**.

---

## 🏛️ Squad Architecture

```
                             ┌────────────────────────┐
                             │    MAIN ORCHESTRATOR   │
                             │  (Zero Inline Coding)  │
                             └───────────┬────────────┘
                                         │
        ┌───────────────┬────────────────┼───────────────┬───────────────┐
        ▼               ▼                ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   BA AGENT   │ │ DESIGN AGENT │ │  DEV AGENT   │ │  DEBUG AGENT │ │   QA AGENT   │
│ Specs & ADRs │ │ Apple HIG/UI │ │Clean Code/TDD│ │Root Cause Fix│ │ SDET & POAI  │
└──────────────┘ └──────────────┘ └──────┬───────┘ └──────────────┘ └──────▲───────┘
                                         │                                 │
                                         └─── HandoffManifest (Self-Test) ─┘
                                         ┌─── DefectTicket (Loopback) ─────┐
                                         │                                 │
```

### The 6 Specialized Squad Roles
1. **`ba-agent` (Technical Business Analyst & Product Architect)**: Requirements elicitation, User Stories, Given-When-Then criteria, and Architecture Decision Records (`ArchitectureDecision`).
2. **`design-agent` (Principal UI/UX Designer)**: Apple HIG compliance, fluid physics, tactile aesthetics, and multi-option interactive HTML mockups (Apple Native, Warm Editorial, Neo-Brutalist).
3. **`dev-agent` (Staff Full-Stack Software Engineer)**: Zero-offloading (writes directly to filesystem), modular composition, TDD, Supabase, and `HandoffManifest` generation.
4. **`debug-agent` (Systems Debugger & Reliability Engineer)**: Root-cause analysis, scientific hypothesis ranking (`Choice`), and minimal surgical patches.
5. **`qa-agent` (Lead QA & Acceptance SDET)**: Black-box acceptance testing, real browser (Playwright) & mobile (Callstack `agent-device`) execution, state mutation verification (POAI), zero source code editing.
6. **`marketing-agent` (Senior Growth Marketer & CRO Specialist)**: Value proposition design, high-converting copy, SEO architecture, and AI slop eradication.

---

## 🧩 Recommended Optional Skills Catalog

The Squad Engine is **completely autonomous and fully functional** even if no external third-party skills are installed.

However, to unlock advanced agent capabilities (e.g. Callstack ADB testing, Apple HIG tokens, TDD scaffolding), the framework recommends the following modular skills:

| Skill | Target Agent | Purpose & Capabilities | Status |
|---|---|---|---|
| `ponytail` | `dev-agent` | Minimalist coding & YAGNI: Stdlib before dependencies, native platform APIs | Optional |
| `safe-refactor` | `dev-agent` / `debug-agent` | Behavior-preserving refactoring with bracketed edits | Optional |
| `composition-patterns` | `dev-agent` | Compound components, custom hooks, avoiding boolean prop hell | Optional |
| `test-driven-development` | `dev-agent` | Red-Green-Refactor scaffolding and deterministic unit tests | Optional |
| `agent-device` | `qa-agent` / `dev-agent` | Callstack mobile automation via semantic accessibility trees (Zero screenshot loops) | Optional |
| `playwright` | `qa-agent` / `dev-agent` | Isolated browser automation with mandatory `try...finally` lifecycle | Optional |
| `accesslint-scan` | `qa-agent` | WCAG accessibility and color contrast ratio audit | Optional |
| `stop-slop` | `qa-agent` / `marketing-agent` | Filters out AI clichés, throat-clearing fluff, and passive phrasing | Optional |
| `ui-ux-pro-max` | `design-agent` | Design intelligence across 50 styles, 21 palettes, and component specs | Optional |
| `apple-design` | `design-agent` | Apple Human Interface Guidelines (HIG), fluid springs, Safe Areas | Optional |
| `huashu-design` | `design-agent` | Spatial hierarchy, glassmorphism, responsive bento grids | Optional |
| `systematic-debugging` | `debug-agent` | Root-cause investigation first before proposing or touching code | Optional |
| `surgical-patch` | `debug-agent` | Narrowest responsible layer bugfix preserving surrounding behavior | Optional |
| `before-you-build` | `ba-agent` | Product risk, demand evaluation, technical feasibility | Optional |
| `writing-plans` | `ba-agent` | Phased implementation plans with explicit human review gates | Optional |
| `avoid-ai-writing` | `marketing-agent` | Audits and rewrites copy to eliminate 21 predictable AI writing patterns | Optional |

### Audit Installed Skills
Run the built-in skill auditor anytime to check local skill availability:
```bash
squad audit-skills
```
> **Customizable & Swappable**: You can install missing skills into your IDE's skills folder or swap them with any equivalent internal skills.

---

## 🔒 Security & Zero-Leak Standards

- **No Committed Secrets**: Never commit API keys to `.env` or version control.
- **Dynamic Configuration Resolver**:
  - **Antigravity**: Keys loaded from `~/.gemini/config/.env`.
  - **Claude Code / Cursor / Codex**: Configured via environment variables (`export TYPESAFE_API_KEY="..."`).
- **Offline Fallback Guarantee**: If no API key is provided, the engine automatically falls back to local regex heuristics with **0 API tokens used**.

---

## 📦 Installation & Setup

Clone the repository:
```bash
git clone https://github.com/VicnovaLabs/VicnovaLabs-squad.git
cd VicnovaLabs-squad
```

### Smart Installer (`installer/install.sh`)

#### A. Live Sync Mode (Author / Active Development)
Creates a symbolic link from your local repo to your global IDE plugin path (`~/.gemini/config/plugins/specialized-squad`):
```bash
./installer/install.sh --target antigravity --dev
```
*(Automatically creates a timestamped backup of existing configurations before linking).*

#### B. Standalone User Mode (Multi-IDE Support)
Install isolated configurations for your specific IDE:
```bash
# Global Antigravity installation (copy mode)
./installer/install.sh --target antigravity

# Local workspace installation
./installer/install.sh --target antigravity --local

# Claude Code (generates CLAUDE.md and settings.json)
./installer/install.sh --target claude

# Cursor (.cursorrules and .cursor/rules/*.mdc)
./installer/install.sh --target cursor

# Codex / OpenAI Universal LLMs (AGENTS.md)
./installer/install.sh --target codex

# Install all IDE integrations
./installer/install.sh --target all
```

---

## ⚡ CLI Reference (`squad` / `jev_triage.py`)

The unified CLI provides 18+ commands accessible via `squad` or `python3 jev_triage.py`:

```bash
# 1. System health, IDE detection, and ADB device check
squad status

# 2. Audit installed skills vs recommended catalog
squad audit-skills

# 3. Classify user intent and determine target squad role
squad triage "create user profile settings screen"

# 4. Suggest squad agent & curated skills (skill-like recommendation without auto-dispatch)
squad suggest "create user profile settings screen"

# 5. Manage & Switch Dispatch Mode (Project vs Session Scoping)
# Or use chat command: /vicnolabs-squad <suggest|smart|auto|inline>
squad mode                         # View current mode & scope
squad mode smart                   # Set mode for project (.squad_mode & .env)
squad mode auto --scope session    # Set mode for active chat session only

# 6. Dispatch task through Unified Gate with configurable dispatch modes
squad dispatch "build Stripe payment checkout endpoint"
# Dispatch modes: --mode suggest (default), --mode smart, --mode auto, --mode inline
squad dispatch "thêm nút copy vào giao diện" --mode suggest
squad dispatch "chạy qa-agent nghiệm thu tính năng search" --mode suggest


# 7. Configure Squad Engine & QA Visual Screenshot Evidence
squad config                                # View full engine configuration
squad config qa-screenshot                  # Check QA screenshot evidence status (Auto-ON by default)
squad config qa-screenshot off              # Disable screenshot archiving
squad config qa-screenshot on               # Re-enable screenshot archiving

# 8. Audit connected ADB emulators vs physical hardware
squad device-audit

# 9. Audit visual & structural fidelity between HTML mockup and component (>= 0.85)
squad ui-audit mock.html src/components/Settings.tsx

# 10. Validate typed handoff payloads (manifest, defect, decision, acceptance)
squad validate-handoff manifest path/to/manifest.json
squad validate-handoff acceptance path/to/receipt.json

# 11. View official JSON Schema specifications
squad get-schema manifest
squad get-schema defect
squad get-schema acceptance

# 12. Scoped Task Plan Engine (.agents/plans/)
squad task-plan init "E2E Checkout Flow" "Cart Validation" "Payment Gateway"
squad task-plan status
squad task-plan update --plan <plan_file> --subtask ST-01 --status DONE --note "Verified"
squad task-plan reconcile

# 13. Subagent watchdog & circuit breaker (detects 429 quota exhaustion and hangs)
squad subagent-watchdog subagents.json
```

---

## 🧪 Verification & Security Audits

Run the complete automated test suite (including security & path leak scanning):
```bash
python3 -m unittest discover tests
```
> **Hermetic & Consolidated**: `tests/test_security_leak.py` is automatically discovered and executed as part of `unittest discover`. All 62 unit tests run hermetically under all dispatch modes (`suggest`, `smart`, `auto`, `inline`) with zero socket leaks.

---

## 📄 License
MIT License. Built with pride by **VicnovaLabs**.
