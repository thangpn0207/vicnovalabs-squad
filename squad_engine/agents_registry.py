#!/usr/bin/env python3
"""
Squad Agents Registry & Definition Loader.
Parses agent markdown definitions into define_subagent compatible payloads.
"""

import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from .config import get_config


def get_agent_definition(role_or_name: str, config=None) -> Dict[str, Any]:
    """Parse agent markdown file into define_subagent schema."""
    if config is None:
        config = get_config()

    raw = role_or_name.lower().replace("_", "-").strip()
    clean_role = raw.replace("squad-", "").replace("-agent", "")
    agents_dir = config.agents_dir

    md_file = agents_dir / f"squad-{clean_role}.md"
    if not md_file.exists():
        md_file = agents_dir / f"{clean_role}-agent.md"
    if not md_file.exists():
        for f in agents_dir.glob("*.md"):
            if f.stem in [f"{clean_role}-agent", f"squad-{clean_role}", clean_role] or f.stem.startswith(clean_role):
                md_file = f
                break

    # Always use squad-<clean_role> for dynamic subagent definitions in Antigravity
    # to avoid collisions with any pre-loaded static read-only plugins.
    name = f"squad-{clean_role}"
    desc = f"Specialized squad agent: {name}"
    system_prompt = f"You are {name}, a specialized squad agent."

    if md_file.exists():
        try:
            content = md_file.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    fm = parts[1]
                    system_prompt = parts[2].strip()
                    for line in fm.splitlines():
                        if line.startswith("description:"):
                            desc = line.split(":", 1)[1].strip()
            else:
                system_prompt = content.strip()
        except Exception:
            pass

    enable_write = any(w in clean_role for w in ["dev", "debug", "design", "qa", "ba", "marketing"])
    return {
        "name": name,
        "description": desc,
        "system_prompt": system_prompt,
        "enable_write_tools": enable_write,
        "enable_mcp_tools": True,
        "enable_subagent_tools": False
    }


def get_all_agent_definitions(config=None) -> Dict[str, Dict[str, Any]]:
    """Return all 6 squad agent definitions keyed by dynamic squad name and legacy alias."""
    roles = ["ba", "design", "dev", "debug", "marketing", "qa"]
    defs = {}
    for r in roles:
        d = get_agent_definition(r, config)
        defs[f"squad-{r}"] = d
        defs[f"{r}-agent"] = d
    return defs


def sync_agents_to_workspace(target_workspace: Optional[str] = None, config=None) -> Dict[str, Any]:
    """Synchronize squad agent definitions into project workspace (.agents/agents/).
    Guards against polluting user home or global configuration directories.
    """
    if config is None:
        config = get_config()

    ws_path = Path(target_workspace).resolve() if target_workspace else Path.cwd().resolve()
    # Guard: never sync to home, root, or global .gemini directory
    if ws_path in [Path.home(), Path.home() / ".gemini", Path("/")]:
        return {
            "status": "SKIPPED",
            "reason": "Refusing to synchronize agents into home or root directory. Please specify an active project workspace.",
            "target_dir": str(ws_path)
        }

    target = ws_path / ".agents" / "agents"
    target.mkdir(parents=True, exist_ok=True)
    src = config.agents_dir
    synced = []
    removed = []

    if src.exists():
        src_names = {f.name for f in src.glob("*.md")}
        # Clean stale or obsolete files in target
        for existing in target.glob("*.md"):
            if existing.name not in src_names:
                existing.unlink()
                removed.append(existing.name)

        for f in src.glob("*.md"):
            dest_file = target / f.name
            shutil.copy2(f, dest_file)
            synced.append(f.name)

    return {
        "status": "SYNCHRONIZED",
        "target_dir": str(target.resolve()),
        "synced_count": len(synced),
        "synced_files": sorted(synced),
        "removed_stale_files": sorted(removed)
    }

