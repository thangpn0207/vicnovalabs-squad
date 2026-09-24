#!/usr/bin/env python3
"""
Squad Dispatch Mode Resolver & Manager for VicnovaLabs Squad.
Supports project-level persistent mode (.squad_mode / .env)
and session-level override (for chat sessions outside of projects or ephemeral sessions).
"""

import os
import re
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

VALID_MODES = ["suggest", "smart", "auto", "inline"]

MODE_DESCRIPTIONS = {
    "suggest": "Suggest squad agents via recommendation cards; defaults to inline execution for speed and token efficiency (Recommended).",
    "smart": "Automatic branching: Inline for simple tasks; suggests for moderate tasks; dispatches subagents for complexity >= 4 or fan-out.",
    "auto": "Fully autonomous: Dispatches dedicated subagents for all domain tasks across the 6 squad roles.",
    "inline": "Direct execution: 100% inline execution on Main Agent with subagent invocations disabled."
}

MODE_COMMAND_REGEX = re.compile(
    r"^\s*/?(?:vicnolabs-squad|vicnovalabs-squad|squad)(?:\s+(?:mode\s+)?([a-zA-Z_-]+))?\s*$",
    re.IGNORECASE
)


def detect_project_workspace(workspace: Optional[str] = None) -> Optional[Path]:
    """
    Detect if the target workspace or current working directory belongs to a valid project.
    Returns the project root Path if found, or None if outside any project.
    """
    start_dir = Path(workspace).resolve() if workspace else Path.cwd().resolve()
    home_dir = Path.home().resolve()

    # Never consider root or home as a project directory
    if start_dir == home_dir or start_dir == Path("/"):
        return None

    # Check upward traversal
    curr = start_dir
    project_markers = [
        "PROJECT_PROGRESS.md",
        ".squad_mode",
        ".squad_config.json",
        ".git",
        "pubspec.yaml",
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "requirements.txt"
    ]

    while curr and curr != home_dir and curr != Path("/"):
        for marker in project_markers:
            target = curr / marker
            if target.exists():
                return curr
        curr = curr.parent

    return None


def detect_session_id() -> Optional[str]:
    """Detect the active conversation / session ID from environment or brain."""
    for key in [
        "ANTIGRAVITY_CONVERSATION_ID",
        "ANTIGRAVITY_SESSION_ID",
        "CLAUDE_CONVERSATION_ID",
        "SESSION_ID"
    ]:
        val = os.environ.get(key)
        if val and val.strip():
            return val.strip()

    # Fallback to Antigravity brain dir if accessible
    brain_dir = Path.home() / ".gemini" / "antigravity" / "brain"
    if brain_dir.exists() and brain_dir.is_dir():
        try:
            subdirs = [d for d in brain_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
            if subdirs:
                latest = max(subdirs, key=lambda d: d.stat().st_mtime)
                return latest.name
        except Exception:
            pass

    return None


def get_session_mode_file(session_id: str) -> Path:
    """Return path to session-specific mode storage file."""
    # If in Antigravity session directory
    agy_brain_session = Path.home() / ".gemini" / "antigravity" / "brain" / session_id
    if agy_brain_session.exists() and agy_brain_session.is_dir():
        return agy_brain_session / "squad_mode.json"

    # Generic squad session storage
    generic_dir = Path.home() / ".squad" / "sessions"
    generic_dir.mkdir(parents=True, exist_ok=True)
    return generic_dir / f"{session_id}.json"


def get_effective_dispatch_mode(
    workspace: Optional[str] = None,
    session_id: Optional[str] = None,
    explicit_mode: Optional[str] = None
) -> Dict[str, Any]:
    """
    Resolve the effective dispatch mode following strict precedence:
    1. Explicit flag (--mode)
    2. Session-specific override
    3. Project config (.squad_mode / .env)
    4. Global environment variable (SQUAD_DISPATCH_MODE)
    5. Context default:
       - Inside project: 'suggest'
       - Outside project (session chat): 'inline' (ưu tiên inline)
    """
    # 1. Explicit argument
    if explicit_mode and explicit_mode.lower().strip() in VALID_MODES:
        norm_mode = explicit_mode.lower().strip()
        return {
            "mode": norm_mode,
            "source": "explicit",
            "is_project": False,
            "project_path": None,
            "session_id": session_id or detect_session_id(),
            "description": MODE_DESCRIPTIONS[norm_mode]
        }

    proj_root = detect_project_workspace(workspace)
    active_session = session_id or detect_session_id()

    # 2. Inside a project: Project config is SSOT
    if proj_root:
        # Check .squad_mode
        mode_file = proj_root / ".squad_mode"
        if mode_file.exists() and mode_file.is_file():
            try:
                pmode = mode_file.read_text(encoding="utf-8").strip().lower()
                if pmode in VALID_MODES:
                    return {
                        "mode": pmode,
                        "source": "project",
                        "is_project": True,
                        "project_path": str(proj_root),
                        "session_id": active_session,
                        "description": MODE_DESCRIPTIONS[pmode]
                    }
            except Exception:
                pass

        # Check project .env
        env_file = proj_root / ".env"
        if env_file.exists() and env_file.is_file():
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("SQUAD_DISPATCH_MODE="):
                            emode = line.split("=", 1)[1].strip().strip('"').strip("'").lower()
                            if emode in VALID_MODES:
                                return {
                                    "mode": emode,
                                    "source": "project_env",
                                    "is_project": True,
                                    "project_path": str(proj_root),
                                    "session_id": active_session,
                                    "description": MODE_DESCRIPTIONS[emode]
                                }
            except Exception:
                pass

        # Check global environment variable
        env_mode = (os.environ.get("SQUAD_DISPATCH_MODE") or "").strip().lower()
        if env_mode in VALID_MODES:
            return {
                "mode": env_mode,
                "source": "global_env",
                "is_project": True,
                "project_path": str(proj_root),
                "session_id": active_session,
                "description": MODE_DESCRIPTIONS[env_mode]
            }

        # Project default: 'suggest'
        return {
            "mode": "suggest",
            "source": "default_project",
            "is_project": True,
            "project_path": str(proj_root),
            "session_id": active_session,
            "description": MODE_DESCRIPTIONS["suggest"]
        }

    # 3. Outside a project (Standalone Chat Session)
    if active_session:
        sf = get_session_mode_file(active_session)
        if sf.exists() and sf.is_file():
            try:
                data = json.loads(sf.read_text(encoding="utf-8"))
                smode = str(data.get("dispatch_mode", "")).lower().strip()
                if smode in VALID_MODES:
                    return {
                        "mode": smode,
                        "source": "session",
                        "is_project": False,
                        "project_path": None,
                        "session_id": active_session,
                        "description": MODE_DESCRIPTIONS[smode]
                    }
            except Exception:
                pass

    # Global environment variable fallback for non-project
    env_mode = (os.environ.get("SQUAD_DISPATCH_MODE") or "").strip().lower()
    if env_mode in VALID_MODES:
        return {
            "mode": env_mode,
            "source": "global_env",
            "is_project": False,
            "project_path": None,
            "session_id": active_session,
            "description": MODE_DESCRIPTIONS[env_mode]
        }

    # Non-project default: priority is 'inline'
    return {
        "mode": "inline",
        "source": "default_non_project",
        "is_project": False,
        "project_path": None,
        "session_id": active_session,
        "description": MODE_DESCRIPTIONS["inline"]
    }


def set_dispatch_mode(
    mode: str,
    workspace: Optional[str] = None,
    session_id: Optional[str] = None,
    scope: Optional[str] = None
) -> Dict[str, Any]:
    """
    Set and persist dispatch mode.
    - If in a project (or scope == 'project'): persists to <project_root>/.squad_mode & .env
    - If outside a project (or scope == 'session'): persists to session storage
    """
    norm_mode = mode.lower().strip()
    if norm_mode not in VALID_MODES:
        return {
            "status": "error",
            "message": f"Invalid mode: '{mode}'. Supported modes: {', '.join(VALID_MODES)}",
            "valid_modes": VALID_MODES
        }

    proj_root = detect_project_workspace(workspace)
    eff_session = session_id or detect_session_id()

    # Determine target scope
    if scope == "session" or (scope is None and proj_root is None):
        target_scope = "session"
        active_id = eff_session or "default_session"
        sf = get_session_mode_file(active_id)
        sf.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "dispatch_mode": norm_mode,
            "session_id": active_id,
            "updated_at": time.time()
        }
        sf.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        card_md = (
            f"> 💬 **Squad Dispatch Mode Configured for Session Chat**\n"
            f"> - **Session ID**: `{active_id}`\n"
            f"> - **New Mode**: `{norm_mode}`\n"
            f"> - **Scope**: Active chat session only (non-project).\n"
            f"> - **Details**: {MODE_DESCRIPTIONS[norm_mode]}"
        )
        return {
            "status": "success",
            "mode": norm_mode,
            "target": "session",
            "session_id": active_id,
            "file": str(sf),
            "card_markdown": card_md,
            "message": f"Applied mode '{norm_mode}' to session chat '{active_id}'."
        }
    else:
        target_scope = "project"
        assert proj_root is not None
        # Write .squad_mode
        mode_file = proj_root / ".squad_mode"
        mode_file.write_text(norm_mode + "\n", encoding="utf-8")

        # Update or append .env if exists
        env_file = proj_root / ".env"
        if env_file.exists() and env_file.is_file():
            try:
                lines = env_file.read_text(encoding="utf-8").splitlines()
                found = False
                new_lines = []
                for l in lines:
                    if l.strip().startswith("SQUAD_DISPATCH_MODE="):
                        new_lines.append(f"SQUAD_DISPATCH_MODE={norm_mode}")
                        found = True
                    else:
                        new_lines.append(l)
                if not found:
                    new_lines.append(f"SQUAD_DISPATCH_MODE={norm_mode}")
                env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            except Exception:
                pass

        card_md = (
            f"> 🎯 **Squad Dispatch Mode Configured for Project**\n"
            f"> - **Project**: `{proj_root.name}` (`{proj_root}`)\n"
            f"> - **New Mode**: `{norm_mode}`\n"
            f"> - **Saved at**: `{proj_root / '.squad_mode'}`\n"
            f"> - **Details**: {MODE_DESCRIPTIONS[norm_mode]}"
        )
        return {
            "status": "success",
            "mode": norm_mode,
            "target": "project",
            "project_root": str(proj_root),
            "file": str(mode_file),
            "card_markdown": card_md,
            "message": f"Configured mode '{norm_mode}' for project '{proj_root.name}'."
        }


def format_mode_status_card(current_info: Dict[str, Any]) -> str:
    """Format markdown status card for current dispatch mode."""
    mode = current_info["mode"]
    source = current_info["source"]
    is_proj = current_info["is_project"]
    proj_path = current_info.get("project_path")
    sess_id = current_info.get("session_id")

    scope_text = f"Project: `{proj_path}`" if is_proj else f"Session Chat: `{sess_id or 'Standalone'}` (Inline priority)"

    options_text = "\n".join([
        f"> - `{m}`{' *(Active)*' if m == mode else ''}: {desc}"
        for m, desc in MODE_DESCRIPTIONS.items()
    ])

    return (
        f"> ⚙️ **VicnovaLabs Squad Dispatch Mode**\n"
        f"> - **Current Mode**: `{mode.upper()}` (Source: `{source}`)\n"
        f"> - **Effective Scope**: {scope_text}\n"
        f">\n"
        f"> **Available Modes:**\n"
        f"{options_text}\n"
        f">\n"
        f"> 💡 **How to switch**: Type `/vicnolabs-squad <mode>` (e.g. `/vicnolabs-squad smart` or `/vicnolabs-squad auto`)."
    )


def handle_squad_mode_prompt(
    prompt: str,
    workspace: Optional[str] = None,
    session_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Check if the prompt is an explicit command to view or set squad dispatch mode.
    Handles:
    - /vicnolabs-squad [mode]
    - /vicnovalabs-squad [mode]
    - /squad mode [mode]
    - /squad [mode]
    """
    if not prompt:
        return None

    clean = prompt.strip()
    match = MODE_COMMAND_REGEX.match(clean)
    if not match:
        # Check alternative phrases like "set squad mode <mode>"
        alt_match = re.match(r"^\s*(?:set\s+)?squad\s+mode\s+([a-zA-Z_-]+)\s*$", clean, re.IGNORECASE)
        if alt_match:
            raw_arg = alt_match.group(1).lower().strip()
        else:
            return None
    else:
        raw_arg = match.group(1)
        if raw_arg:
            raw_arg = raw_arg.lower().strip()

    # If no argument or 'status' / 'help' / 'mode': show current status
    if not raw_arg or raw_arg in ["status", "help", "mode", "info"]:
        current_info = get_effective_dispatch_mode(workspace, session_id)
        card_md = format_mode_status_card(current_info)
        return {
            "status": "success",
            "execution_mode": "inline",
            "decision": "QUERY_SQUAD_MODE",
            "action": "status",
            "mode": current_info["mode"],
            "info": current_info,
            "dispatch_card_markdown": card_md,
            "auto_chain": False
        }

    # If argument is one of the valid modes:
    if raw_arg in VALID_MODES:
        set_res = set_dispatch_mode(raw_arg, workspace, session_id)
        return {
            "status": "success",
            "execution_mode": "inline",
            "decision": "SET_SQUAD_MODE",
            "action": "set",
            "mode": raw_arg,
            "target": set_res.get("target"),
            "dispatch_card_markdown": set_res.get("card_markdown"),
            "details": set_res,
            "auto_chain": False
        }

    # If invalid argument
    current_info = get_effective_dispatch_mode(workspace, session_id)
    card_md = (
        f"> ⚠️ **Invalid Mode**: `{raw_arg}`\n"
        f"> Valid modes: `suggest`, `smart`, `auto`, `inline`.\n"
        f"> Type `/vicnolabs-squad <mode>` to update."
    )
    return {
        "status": "error",
        "execution_mode": "inline",
        "decision": "INVALID_SQUAD_MODE",
        "action": "error",
        "mode": current_info["mode"],
        "dispatch_card_markdown": card_md,
        "auto_chain": False
    }
