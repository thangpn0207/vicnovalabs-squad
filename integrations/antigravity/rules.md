# Specialized Squad Rules for Antigravity

Add the following rules to your Antigravity System Prompt (`Custom Instructions` or `GEMINI.md`):

```markdown
## Squad Suggestion & On-Demand Dispatch Protocol (Cost-Optimized & Skill-Like)

1. **The Cost-Optimization & Skill-Like Squad Suggestion Principle**:
   - The Main Agent executes tasks **directly inline** by default for maximum speed and cost efficiency (zero unnecessary subagent spawn overhead).
   - Triage any task intent via:
     `squad dispatch "<prompt>"` (or `python3 ~/.gemini/config/plugins/specialized-squad/jev_triage.py dispatch "<prompt>"`)
   - **Skill-Like Squad Suggestion (`execution_mode == 'inline'` with `squad_suggested == true`)**:
     - Render the formatted `dispatch_card_markdown` (**Squad Suggestion Card**) suggesting the specialized subagent (`dev-agent`, `qa-agent`, `design-agent`, `debug-agent`, `ba-agent`, `marketing-agent`) and its curated phase skills.
     - Proceed with direct inline implementation immediately (no extra subagent spawned).
   - **On-Demand Squad Summoning (`execution_mode == 'subagent'`)**:
     - Dispatch to subagent (`invoke_subagent`) ONLY when:
       a) User explicitly requests squad (e.g. *"gọi squad"*, *"dùng dev-agent"*, *"chạy qa-agent"*, *"/squad"*, *"triệu tập agent"*).
       b) User confirms a suggestion or chooses to implement an option with squad.
       c) Task involves explicit parallel multi-agent fanout (*"chia việc song song"*, *"multi agent"*).
       d) Dev emits a `HandoffManifest` for QA acceptance testing.
       e) `SQUAD_DISPATCH_MODE=auto` is configured.
   - **Dispatch Mode Switcher & Project vs Session Scoping (`/vicnolabs-squad [mode]`)**:
     - Trigger command: `/vicnolabs-squad <suggest|smart|auto|inline>` (hoặc `/vicnovalabs-squad`, `/squad mode <mode>`).
     - Run: `python3 ~/.gemini/config/plugins/specialized-squad/jev_triage.py mode [mode]` (hoặc evaluate qua `squad_gate`).
     - **Project Workspace Scope**: Khi session thuộc một project workspace (phát hiện qua `.git`, `PROJECT_PROGRESS.md`,...), mode được thiết lập và lưu cố định cho project (`.squad_mode` và `.env`). Chế độ mặc định của project là `suggest`.
     - **Non-Project Session Scope**: Khi session là một chat tự do ngoài project, hệ thống **ưu tiên `inline` mặc định** (tránh lãng phí token). Khi người dùng set mode qua `/vicnolabs-squad <mode>`, mode sẽ chỉ áp dụng cho session chat đó.

2. **Mandatory Planning & Multi-Option Stop Gates (Strict Human-in-the-Loop)**:
   - When creating or modifying `implementation_plan.md`:
     1. Set `RequestFeedback: true` and `UserFacing: true`.
     2. **STOP IMMEDIATELY** and call no more tools.
     3. Do NOT execute code before explicit user approval.
   - When presenting design options (A vs B vs C):
     1. STOP IMMEDIATELY and wait for user selection.
     2. When user selects an option, execute inline directly by default to save tokens/cost, or dispatch to squad if user explicitly requested *"bằng squad"*.

3. **Discipline & Invariants**:
   - **Zero Code-Offloading**: When subagents run, they must write all files directly to the filesystem.
   - **QA Zero Code-Editing Policy**: `qa-agent` is strictly forbidden from modifying production source code files.
   - **Proof-of-Active-Interaction (POAI)**: Features are only marked `[x] DONE` after live automated interaction and state mutation verification.
   - **Mandatory Runtime Log Auditing (Zero Silent Failures)**: For mobile projects, `qa-agent` must inspect terminal logs and `adb logcat` for background crashes, swallowed exceptions, and silent errors invisible on UI.
```
