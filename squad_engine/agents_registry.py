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

    role = role_or_name.lower().replace("_", "-")
    name = role if role.endswith("-agent") else f"{role}-agent"
    agents_dir = config.agents_dir

    md_file = agents_dir / f"{name}.md"
    if not md_file.exists():
        for f in agents_dir.glob("*.md"):
            if f.stem == name or f.stem.startswith(role):
                md_file = f
                break

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
                        elif line.startswith("name:"):
                            name = line.split(":", 1)[1].strip()
            else:
                system_prompt = content.strip()
        except Exception:
            pass

    enable_write = any(w in name for w in ["dev", "debug", "design"])
    return {
        "name": name,
        "description": desc,
        "system_prompt": system_prompt,
        "enable_write_tools": enable_write,
        "enable_mcp_tools": True,
        "enable_subagent_tools": False
    }


def get_all_agent_definitions(config=None) -> Dict[str, Dict[str, Any]]:
    """Return all 6 squad agent definitions."""
    roles = ["ba", "design", "dev", "debug", "marketing", "qa"]
    return {f"{r}-agent": get_agent_definition(r, config) for r in roles}


def sync_agents_to_workspace(target_workspace: Optional[str] = None, config=None) -> Dict[str, Any]:
    """Synchronize squad agent definitions into workspace (.agents/agents/)."""
    if config is None:
        config = get_config()

    target = Path(target_workspace) if target_workspace else Path.cwd() / ".agents" / "agents"
    target.mkdir(parents=True, exist_ok=True)
    src = config.agents_dir
    synced = []

    if src.exists():
        for f in src.glob("*.md"):
            dest_file = target / f.name
            shutil.copy2(f, dest_file)
            synced.append(f.name)

    return {
        "status": "SYNCHRONIZED",
        "target_dir": str(target.resolve()),
        "synced_count": len(synced),
        "synced_files": sorted(synced)
    }
