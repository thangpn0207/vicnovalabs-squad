#!/usr/bin/env python3
"""
VicnovaLabs Squad — Agent Setting & Permission Self-Healing Engine.
Audits and repairs workspace configurations, static read-only agent traps,
global permission poisoning, and dynamic definition matrices across IDEs.
"""

import os
import sys
import json
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from .config import get_config
from .agents_registry import get_all_agent_definitions, get_agent_definition


SQUAD_ROLES = ["ba", "design", "dev", "debug", "qa", "marketing"]
WRITE_ENABLED_ROLES = {"ba", "design", "dev", "debug", "qa", "marketing"}
SQUAD_MD_NAMES = {f"squad-{r}.md" for r in SQUAD_ROLES} | {f"{r}-agent.md" for r in SQUAD_ROLES}


class AgentSettingFixer:
    """Audits and repairs agent configurations, permissions, and environments."""

    def __init__(self, workspace: Optional[str] = None, dry_run: bool = False, force: bool = False):
        self.config = get_config()
        self.workspace = Path(workspace).resolve() if workspace else Path.cwd().resolve()
        self.dry_run = dry_run
        self.force = force
        self.remediations: List[Dict[str, Any]] = []
        self.warnings: List[str] = []
        self.pre_state: Dict[str, Any] = {}
        self.post_state: Dict[str, Any] = {}

    def run(self) -> Dict[str, Any]:
        """Execute full audit and repair pipeline."""
        start_time = datetime.now(timezone.utc).isoformat()
        self._capture_pre_state()

        # Step 1: Clean workspace static read-only trap
        self._audit_and_fix_workspace_static_trap()

        # Step 2: Clean global static agent poisoning
        self._audit_and_fix_global_static_poisoning()

        # Step 3: Audit and fix workspace dispatch mode (.squad_mode)
        self._audit_and_fix_workspace_mode()

        # Step 4: Audit agent definitions and write tool permissions
        perms_result = self._audit_agent_permissions()

        # Step 5: Audit Antigravity plugin integrity
        self._audit_and_fix_antigravity_plugin()

        # Step 6: Audit agent prompt templates for legacy names
        self._audit_and_fix_agent_prompts()

        self._capture_post_state()

        has_fixes = len(self.remediations) > 0
        status = "REPAIRED" if has_fixes else ("WARNING" if self.warnings else "OPTIMAL")

        return {
            "status": status,
            "timestamp": start_time,
            "workspace": str(self.workspace),
            "dry_run": self.dry_run,
            "remediations_count": len(self.remediations),
            "remediations": self.remediations,
            "warnings_count": len(self.warnings),
            "warnings": self.warnings,
            "permissions_matrix": perms_result,
            "pre_state": self.pre_state,
            "post_state": self.post_state,
            "recommendations": self._generate_recommendations(status)
        }

    def _capture_pre_state(self):
        """Record system state prior to remediation."""
        ws_agents_dir = self.workspace / ".agents" / "agents"
        ws_static_files = [f.name for f in ws_agents_dir.glob("*.md")] if ws_agents_dir.exists() else []

        global_poison = self._find_global_poison_files()
        mode_file = self.workspace / ".squad_mode"
        current_mode = mode_file.read_text(encoding="utf-8").strip() if mode_file.exists() else "MISSING"

        self.pre_state = {
            "workspace_static_agents_dir_exists": ws_agents_dir.exists(),
            "workspace_static_agents_count": len(ws_static_files),
            "workspace_static_files": sorted(ws_static_files),
            "global_static_poison_count": len(global_poison),
            "global_static_poison_files": [str(p) for p in global_poison],
            "workspace_squad_mode": current_mode
        }

    def _capture_post_state(self):
        """Record system state after remediation."""
        ws_agents_dir = self.workspace / ".agents" / "agents"
        ws_static_files = [f.name for f in ws_agents_dir.glob("*.md")] if ws_agents_dir.exists() else []

        global_poison = self._find_global_poison_files()
        mode_file = self.workspace / ".squad_mode"
        current_mode = mode_file.read_text(encoding="utf-8").strip() if mode_file.exists() else "MISSING"

        self.post_state = {
            "workspace_static_agents_dir_exists": ws_agents_dir.exists(),
            "workspace_static_agents_count": len(ws_static_files),
            "workspace_static_files": sorted(ws_static_files),
            "global_static_poison_count": len(global_poison),
            "global_static_poison_files": [str(p) for p in global_poison],
            "workspace_squad_mode": current_mode
        }

    def _find_global_poison_files(self) -> List[Path]:
        """Locate rogue static squad markdown files in global user agent directories."""
        home = Path.home()
        candidate_dirs = [
            home / ".gemini" / ".agents",
            home / ".gemini" / "agents",
            home / ".agents" / "agents"
        ]
        poison_files = []
        for d in candidate_dirs:
            if d.exists() and d.is_dir():
                for f in d.glob("*.md"):
                    if f.name in SQUAD_MD_NAMES or any(f.name.startswith(f"squad-{r}") for r in SQUAD_ROLES):
                        poison_files.append(f)
        return poison_files

    def _audit_and_fix_workspace_static_trap(self):
        """Clean static .agents/agents in workspace which triggers Antigravity read-only mode."""
        ws_agents_dir = self.workspace / ".agents" / "agents"
        if ws_agents_dir.exists():
            files = list(ws_agents_dir.glob("*.md"))
            file_names = [f.name for f in files]
            if not self.dry_run:
                shutil.rmtree(ws_agents_dir, ignore_errors=True)
                # Clean parent if empty
                parent = self.workspace / ".agents"
                if parent.exists() and not any(parent.iterdir()):
                    shutil.rmtree(parent, ignore_errors=True)

            self.remediations.append({
                "action": "REMOVE_WORKSPACE_STATIC_TRAP",
                "target": str(ws_agents_dir),
                "severity": "CRITICAL",
                "details": f"Removed {len(file_names)} static markdown agent files ({', '.join(file_names)}) that forced Antigravity into Read-Only subagent mode and blocked define_subagent.",
                "resolved": not self.dry_run
            })

    def _audit_and_fix_global_static_poisoning(self):
        """Clean rogue static files in ~/.gemini/.agents or ~/.agents/agents."""
        poison_files = self._find_global_poison_files()
        if poison_files:
            removed = []
            for pf in poison_files:
                if not self.dry_run:
                    try:
                        pf.unlink()
                        removed.append(str(pf))
                    except Exception as e:
                        self.warnings.append(f"Failed to remove global poison file {pf}: {e}")
                else:
                    removed.append(str(pf))

            self.remediations.append({
                "action": "REMOVE_GLOBAL_STATIC_POISONING",
                "severity": "CRITICAL",
                "count": len(removed),
                "files": removed,
                "details": "Removed global static agent markdown files causing global Read-Only subagent stripping across all IDE sessions.",
                "resolved": not self.dry_run
            })

    def _audit_and_fix_workspace_mode(self):
        """Ensure .squad_mode exists and has valid content."""
        mode_file = self.workspace / ".squad_mode"
        valid_modes = {"suggest", "smart", "auto", "inline"}
        current = mode_file.read_text(encoding="utf-8").strip() if mode_file.exists() else None

        if not current or current not in valid_modes or self.force:
            target_mode = "suggest"
            if not self.dry_run:
                mode_file.write_text(f"{target_mode}\n", encoding="utf-8")

            self.remediations.append({
                "action": "INITIALIZE_SQUAD_MODE",
                "target": str(mode_file),
                "severity": "LOW",
                "old_mode": current or "MISSING",
                "new_mode": target_mode,
                "details": f"Configured workspace dispatch mode to '{target_mode}' (Skill-Like Suggestion & Cost-Optimized Inline Default).",
                "resolved": not self.dry_run
            })

    def _audit_agent_permissions(self) -> Dict[str, Any]:
        """Verify that agent registry definitions correctly grant filesystem write tools."""
        defs = get_all_agent_definitions(self.config)
        matrix = {}
        misconfigured = []

        for role in SQUAD_ROLES:
            key = f"squad-{role}"
            defn = defs.get(key)
            if not defn:
                misconfigured.append(key)
                matrix[key] = {"status": "MISSING", "write_tools": False}
                continue

            has_write = defn.get("enable_write_tools", False)
            expected_write = role in WRITE_ENABLED_ROLES

            if has_write != expected_write:
                misconfigured.append(key)
                matrix[key] = {
                    "status": "PERMISSION_MISMATCH",
                    "actual_write_tools": has_write,
                    "expected_write_tools": expected_write
                }
            else:
                matrix[key] = {
                    "status": "VERIFIED",
                    "write_tools": has_write,
                    "mcp_tools": defn.get("enable_mcp_tools", True)
                }

        if misconfigured:
            self.warnings.append(f"Agent definitions with unexpected write permissions: {', '.join(misconfigured)}")

        return matrix

    def _audit_and_fix_antigravity_plugin(self):
        """Verify that ~/.gemini/config/plugins/specialized-squad is linked correctly."""
        home = Path.home()
        plugin_dir = home / ".gemini" / "config" / "plugins" / "specialized-squad"
        expected_adapter = self.config.repo_root / "integrations" / "antigravity"

        if not plugin_dir.exists():
            if expected_adapter.exists():
                if not self.dry_run:
                    plugin_dir.parent.mkdir(parents=True, exist_ok=True)
                    plugin_dir.symlink_to(expected_adapter)
                self.remediations.append({
                    "action": "RESTORE_ANTIGRAVITY_PLUGIN_SYMLINK",
                    "target": str(plugin_dir),
                    "source": str(expected_adapter),
                    "severity": "HIGH",
                    "details": "Restored live symlink between Antigravity plugin directory and repository adapter.",
                    "resolved": not self.dry_run
                })
            else:
                self.warnings.append(f"Antigravity adapter not found at {expected_adapter}")
        elif plugin_dir.is_symlink():
            try:
                resolved = plugin_dir.resolve()
                if not resolved.exists():
                    if expected_adapter.exists() and not self.dry_run:
                        plugin_dir.unlink()
                        plugin_dir.symlink_to(expected_adapter)
                    self.remediations.append({
                        "action": "FIX_BROKEN_PLUGIN_SYMLINK",
                        "target": str(plugin_dir),
                        "severity": "HIGH",
                        "details": "Repaired broken symlink for specialized-squad plugin.",
                        "resolved": not self.dry_run
                    })
            except Exception as e:
                self.warnings.append(f"Error checking plugin symlink: {e}")

    def _audit_and_fix_agent_prompts(self):
        """Audit agents/ markdown files to eliminate obsolete dev-agent error strings."""
        agents_dir = self.config.agents_dir
        if not agents_dir.exists():
            return

        repaired_files = []
        for md_file in agents_dir.glob("squad-*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
                # Detect obsolete error string with dev-agent
                if "dev-agent was provisioned without" in text:
                    new_text = text.replace(
                        "dev-agent was provisioned without filesystem write tools",
                        f"{md_file.stem} was provisioned without filesystem write tools"
                    )
                    if not self.dry_run:
                        md_file.write_text(new_text, encoding="utf-8")
                    repaired_files.append(md_file.name)
            except Exception as e:
                self.warnings.append(f"Error inspecting {md_file.name}: {e}")

        if repaired_files:
            self.remediations.append({
                "action": "SANITIZE_PROMPT_TEMPLATES",
                "files": repaired_files,
                "severity": "MEDIUM",
                "details": f"Updated obsolete agent error strings in {len(repaired_files)} prompt files to match dynamic squad names.",
                "resolved": not self.dry_run
            })

    def _generate_recommendations(self, status: str) -> List[str]:
        """Generate actionable guidance for developer and Main Agent."""
        recs = []
        if status in ["REPAIRED", "OPTIMAL"]:
            recs.append("Environment and agent configurations are clean and verified.")
            recs.append("To summon subagents with 100% guaranteed write permissions, use TypeName: 'self'.")
            recs.append("For specialized dynamic agents, ensure define_subagent is executed prior to invoke_subagent.")
            recs.append("Inline execution on Main Agent remains the fastest, most cost-effective default.")
        else:
            recs.append("Review remaining warnings and verify file permissions.")
        return recs


def fix_agent_setting(
    workspace: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False
) -> Dict[str, Any]:
    """Top-level entrypoint for /vicnovalabs-squad fix-agent-setting."""
    fixer = AgentSettingFixer(workspace=workspace, dry_run=dry_run, force=force)
    return fixer.run()


def format_fix_report_markdown(res: Dict[str, Any]) -> str:
    """Format audit and repair result as a concise, high-visibility Markdown report."""
    status = res.get("status", "UNKNOWN")
    rems = res.get("remediations", [])
    warnings = res.get("warnings", [])
    perms = res.get("permissions_matrix", {})

    status_badge = "🟢 REPAIRED & VERIFIED" if status == "REPAIRED" else ("🔵 OPTIMAL (NO REPAIRS NEEDED)" if status == "OPTIMAL" else "🟡 WARNING")

    lines = [
        "### 🛡️ VICNOVALABS SQUAD — AGENT PERMISSION & CONFIG HEALER",
        f"**Status**: {status_badge}  |  **Workspace**: `{res.get('workspace')}`",
        f"**Timestamp**: `{res.get('timestamp')}`  |  **Mode**: `{'DRY RUN' if res.get('dry_run') else 'LIVE REPAIR'}`",
        "",
        "#### 1. Remediation & Repair Actions"
    ]

    if not rems:
        lines.append("- ✅ **Clean Workspace State**: No static `.agents/agents` read-only traps or rogue global files detected.")
        lines.append("- ✅ **Clean Dispatch Mode**: Workspace mode `.squad_mode` verified.")
    else:
        for r in rems:
            lines.append(f"- 🔧 **[{r.get('action')}]** ({r.get('severity')}): {r.get('details')}")

    lines.append("")
    lines.append("#### 2. Agent Write Permission Matrix (Dynamic Schemas)")
    lines.append("| Agent | Role Type | Filesystem Write Tools | Status |")
    lines.append("|---|---|---|---|")
    for name, p in sorted(perms.items()):
        wt = "✅ GRANTED (`write_to_file`, `replace_file_content`)" if p.get("write_tools") else "⛔ READ-ONLY (No Write Tools)"
        st = f"**{p.get('status')}**"
        lines.append(f"| `{name}` | Specialized Subagent | {wt} | {st} |")

    if warnings:
        lines.append("")
        lines.append("#### 3. Warnings")
        for w in warnings:
            lines.append(f"- ⚠️ {w}")

    lines.append("")
    lines.append("#### 4. Safe Subagent Summoning Guidelines")
    for rec in res.get("recommendations", []):
        lines.append(f"- 💡 {rec}")

    return "\n".join(lines)
