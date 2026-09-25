---
name: squad-triage
description: System One Triage, intent classification, complexity scoring, and dynamic skill matrix for AI IDEs
role: Triage & Router
phase: dispatch
version: 2.0.0
---

# Squad Triage & Dispatching Skill

Use this skill to determine which specialized squad agent should handle a given user prompt, what phase skills to load, and whether inline execution is permitted.

## Usage
Run triage from terminal or agent runner:
```bash
squad dispatch "<user_prompt>"
```

## Triage Classification Rules
1. **Requirements & Scope** (`spec`, `story`, `criteria`, `plan`, `đặc tả`) $\rightarrow$ `squad-ba`
2. **UI/UX & Visual Mockups** (`mockup`, `design`, `layout`, `css`, `giao diện`) $\rightarrow$ `squad-design`
3. **Feature Code & Architecture** (`implement`, `build`, `api`, `endpoint`, `database`, `viết code`) $\rightarrow$ `squad-dev`
4. **Bug & Crash Investigation** (`bug`, `error`, `crash`, `stack trace`, `lỗi`) $\rightarrow$ `squad-debug`
5. **Acceptance Testing & Verification** (`qa`, `test`, `acceptance`, `nghiệm thu`, `verify`) $\rightarrow$ `squad-qa`
6. **Marketing & Copywriting** (`copy`, `seo`, `landing page`, `cta`, `quảng cáo`) $\rightarrow$ `squad-marketing`

## Fast-Path / Inline Exemption Rule
Inline execution is strictly restricted to:
- Single-token or typo fixes in 1 known file.
- Single `.env` variable key updates or dependency version bumps.
- Pure informational Q&A without code modifications.
Everything else MUST be delegated to the specialized agent.

## Self-Healing Command
```bash
# Slash command in chat
/vicnovalabs-squad fix-agent-setting

# CLI execution
squad fix-agent-setting
```
Audits and fixes subagent permissions, removes workspace static traps, and restores valid `.squad_mode`.
