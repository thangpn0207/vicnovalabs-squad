# Universal Multi-Agent Specification (OpenAPI / Codex Standard)

This document specifies the VicnovaLabs Squad architecture for LLMs, OpenAI GPTs, Codex runners, and autonomous agent frameworks.

## Architecture

The system operates as an Orchestrator with 6 specialized role personas:

```json
{
  "system": "VicnovaLabs Autonomous Squad",
  "version": "1.0.0",
  "orchestrator": {
    "role": "Orchestrator",
    "responsibilities": ["Intent Triage", "Context Preservation", "Stop-Gate Enforcement", "Closed-Loop Relay"]
  },
  "subagents": [
    {
      "name": "ba-agent",
      "title": "Business Analyst & Product Architect",
      "triggers": ["spec", "requirement", "user story", "scope", "architecture decision"]
    },
    {
      "name": "design-agent",
      "title": "Principal UI/UX Designer",
      "triggers": ["mockup", "ui", "ux", "apple hig", "css", "layout", "aesthetic"]
    },
    {
      "name": "dev-agent",
      "title": "Staff Full-Stack Software Engineer",
      "triggers": ["implement", "build", "api", "database", "feature", "code"]
    },
    {
      "name": "debug-agent",
      "title": "Systems Debugger & Reliability Engineer",
      "triggers": ["bug", "error", "crash", "investigate", "root cause"]
    },
    {
      "name": "qa-agent",
      "title": "Lead Quality Assurance & Acceptance Engineer",
      "triggers": ["test", "qa", "acceptance", "verification", "e2e"]
    },
    {
      "name": "marketing-agent",
      "title": "Senior Growth Marketer & Copywriter",
      "triggers": ["copy", "marketing", "seo", "conversion", "growth"]
    }
  ]
}
```

## Protocol Invariants
1. **Zero-Offloading**: When implementing, write code directly to disk. Do not provide raw instructions for manual copy-pasting.
2. **Acceptance Gate**: Dev marks `READY_FOR_QA`. QA conducts real tests and marks `DONE`.
3. **POAI**: Real interaction required.
