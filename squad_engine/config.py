#!/usr/bin/env python3
"""
Dynamic Configuration Loader for VicnovaLabs Squad.
Zero hardcoding: resolves paths dynamically via SQUAD_HOME, repo root, or home directory.
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any


class SquadConfig:
    """Central configuration resolver for Squad Engine across multiple IDEs."""

    def __init__(self, squad_home: Optional[str] = None):
        self.home_dir = Path.home()
        self.repo_root = self._detect_repo_root()
        self.squad_home = self._resolve_squad_home(squad_home)
        self.env_data = self._load_env_file()

    def _detect_repo_root(self) -> Path:
        """Locate root of VicnovaLabs-squad repository."""
        current = Path(__file__).resolve().parent.parent
        if (current / "squad_engine").exists() and (current / "agents").exists():
            return current
        # Check current working directory
        cwd = Path.cwd()
        if (cwd / "squad_engine").exists() and (cwd / "agents").exists():
            return cwd
        return current

    def _resolve_squad_home(self, explicit_home: Optional[str] = None) -> Path:
        """Resolve squad configuration and assets directory."""
        if explicit_home and explicit_home.strip():
            return Path(explicit_home).resolve()
        
        env_home = os.environ.get("SQUAD_HOME") or os.environ.get("VicnovaLabs_SQUAD_DIR")
        if env_home and env_home.strip():
            return Path(env_home).resolve()

        # If running from inside the repo
        if (self.repo_root / "agents").exists():
            return self.repo_root

        # Fallbacks in user home
        standard_squad = self.home_dir / ".squad"
        if standard_squad.exists():
            return standard_squad

        gemini_plugin = self.home_dir / ".gemini" / "config" / "plugins" / "specialized-squad"
        if gemini_plugin.exists():
            return gemini_plugin

        return self.repo_root

    def _load_env_file(self) -> Dict[str, str]:
        """Load environment variables from nearest .env file."""
        env_dict = {}
        candidate_paths = [
            self.squad_home / ".env",
            self.repo_root / ".env",
            self.home_dir / ".squad" / ".env",
            self.home_dir / ".gemini" / "config" / ".env"
        ]
        
        for p in reversed(candidate_paths):
            if p.exists() and p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#") or "=" not in line:
                                continue
                            k, v = line.split("=", 1)
                            env_dict[k.strip()] = v.strip().strip('"').strip("'")
                except Exception:
                    pass
        return env_dict

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get env variable with priority: os.environ > .env file > default."""
        return os.environ.get(key) or self.env_data.get(key, default)

    @property
    def agents_dir(self) -> Path:
        candidates = [
            self.squad_home / "agents",
            self.repo_root / "agents",
            self.home_dir / ".squad" / "agents",
            self.home_dir / ".gemini" / "config" / "plugins" / "specialized-squad" / "definitions",
            self.home_dir / ".gemini" / "config" / "plugins" / "specialized-squad" / "agents"
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                return c
        return self.repo_root / "agents"

    @property
    def skills_dir(self) -> Path:
        candidates = [
            self.squad_home / "skills",
            self.repo_root / "skills",
            self.home_dir / ".squad" / "skills",
            self.home_dir / ".agents" / "skills"
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                return c
        return self.repo_root / "skills"

    @property
    def typesafe_api_key(self) -> Optional[str]:
        return self.get("TYPESAFE_API_KEY")

    @property
    def dispatch_mode(self) -> str:
        """
        Squad dispatch mode:
        - 'suggest': Suggest squad like a skill card; default to inline execution for low-cost, fast work unless explicitly invoked (DEFAULT).
        - 'smart': Auto-dispatch for complexity >= 4 or composite fanout; suggest for 2-3; inline for 1.
        - 'auto': Legacy behavior; always auto-dispatch subagents for domain tasks.
        - 'inline': Always run inline directly without subagents.
        """
        try:
            from .mode import get_effective_dispatch_mode
            info = get_effective_dispatch_mode()
            return info["mode"]
        except Exception:
            mode = (self.get("SQUAD_DISPATCH_MODE") or "suggest").lower().strip()
            if mode not in ["suggest", "smart", "auto", "inline"]:
                return "suggest"
            return mode

    @property
    def qa_screenshot_evidence(self) -> bool:
        """
        Flag controlling whether QA automatically captures screenshot visual evidence upon test completion.
        Defaults to True (auto-enabled). Can be set to False via:
        - Env var QA_SCREENSHOT_EVIDENCE=false / 0 / off
        - .env / .squad_config QA_SCREENSHOT_EVIDENCE=false
        """
        val = self.get("QA_SCREENSHOT_EVIDENCE")
        if val is None:
            return True
        val_str = str(val).lower().strip()
        if val_str in ["0", "false", "off", "no", "disable", "disabled"]:
            return False
        return True

    def detect_active_ide(self) -> str:
        """Detect current IDE running the squad."""
        if os.environ.get("ANTIGRAVITY_SESSION_ID") or (self.home_dir / ".gemini" / "antigravity").exists():
            return "antigravity"
        if os.environ.get("CLAUDE_CODE") or os.environ.get("ANTHROPIC_API_KEY"):
            return "claude_code"
        if os.environ.get("CURSOR_PROJECT_DIR") or Path(".cursor").exists():
            return "cursor"
        if os.environ.get("CODEX_ENV"):
            return "codex"
        return "generic_cli"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "squad_home": str(self.squad_home),
            "repo_root": str(self.repo_root),
            "agents_dir": str(self.agents_dir),
            "skills_dir": str(self.skills_dir),
            "dispatch_mode": self.dispatch_mode,
            "qa_screenshot_evidence": self.qa_screenshot_evidence,
            "has_typesafe_key": bool(self.typesafe_api_key),
            "detected_ide": self.detect_active_ide(),
            "env_loaded_from": [str(k) for k in self.env_data.keys()]
        }


# Global singleton instance
_GLOBAL_CONFIG: Optional[SquadConfig] = None

def get_config(squad_home: Optional[str] = None) -> SquadConfig:
    global _GLOBAL_CONFIG
    if _GLOBAL_CONFIG is None or squad_home is not None:
        _GLOBAL_CONFIG = SquadConfig(squad_home)
    return _GLOBAL_CONFIG


def is_qa_screenshot_enabled(workspace: Optional[str] = None) -> bool:
    """Check if QA screenshot evidence archiving is enabled (defaults to True)."""
    cfg = get_config()
    return cfg.qa_screenshot_evidence


def set_qa_screenshot_config(enabled: bool, workspace: Optional[str] = None) -> Dict[str, Any]:
    """Persist QA screenshot evidence configuration to project .env and environment."""
    from .mode import detect_project_workspace
    proj_root = detect_project_workspace(workspace) or Path.cwd()
    env_file = proj_root / ".env"
    val_str = "true" if enabled else "false"
    
    os.environ["QA_SCREENSHOT_EVIDENCE"] = val_str
    
    lines = []
    found = False
    if env_file.exists() and env_file.is_file():
        try:
            lines = env_file.read_text(encoding="utf-8").splitlines()
            new_lines = []
            for l in lines:
                if l.strip().startswith("QA_SCREENSHOT_EVIDENCE="):
                    new_lines.append(f"QA_SCREENSHOT_EVIDENCE={val_str}")
                    found = True
                else:
                    new_lines.append(l)
            lines = new_lines
        except Exception:
            lines = []
    if not found:
        lines.append(f"QA_SCREENSHOT_EVIDENCE={val_str}")
    
    try:
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass
        
    global _GLOBAL_CONFIG
    _GLOBAL_CONFIG = None
    
    return {
        "status": "success",
        "qa_screenshot_evidence": enabled,
        "saved_to": str(env_file),
        "message": f"QA visual screenshot evidence set to {'ON' if enabled else 'OFF'}."
    }

