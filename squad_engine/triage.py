#!/usr/bin/env python3
"""
Intent Classification, Complexity Scoring, and Dynamic Skill Profiling.
Supports Jev AI TypeSafe System One semantic triage with robust offline fallback heuristics.
"""

import re
import sys
from typing import Dict, Any, List, Optional
from .devices import audit_adb_devices, is_hardware_constrained, is_device_resume_prompt
from .handoffs import format_dispatch_card


PHASE_SKILL_PROFILES = {
    "dev": {
        "coding": [
            "ponytail",
            "safe-refactor",
            "composition-patterns",
            "test-driven-development"
        ],
        "self_test_mobile": [
            "agent-device"
        ],
        "self_test_web": [
            "playwright",
            "accesslint-scan"
        ]
    },
    "qa": {
        "acceptance_mobile": [
            "agent-device",
            "stop-slop"
        ],
        "hybrid_dual_device_qa": [
            "agent-device",
            "accesslint-scan",
            "stop-slop"
        ],
        "acceptance_web": [
            "playwright",
            "accesslint-scan",
            "stop-slop"
        ]
    },
    "debug": {
        "investigation": [
            "systematic-debugging",
            "surgical-patch"
        ]
    },
    "design": {
        "prototyping_mobile": [
            "ui-ux-pro-max",
            "apple-design"
        ],
        "prototyping_web": [
            "ui-ux-pro-max",
            "huashu-design"
        ]
    },
    "ba": {
        "requirements": [
            "before-you-build",
            "writing-plans"
        ]
    },
    "marketing": {
        "copywriting": [
            "avoid-ai-writing",
            "marketing-plan"
        ]
    }
}


RECOMMENDED_SKILLS_CATALOG = {
    "ponytail": {
        "role": "dev-agent",
        "description": "Minimalist coding & YAGNI: Stdlib before external dependencies, native APIs first"
    },
    "safe-refactor": {
        "role": "dev-agent / debug-agent",
        "description": "Behavior-preserving refactoring with bracketed edits"
    },
    "composition-patterns": {
        "role": "dev-agent",
        "description": "Compound components, custom hooks, avoiding boolean prop hell"
    },
    "test-driven-development": {
        "role": "dev-agent",
        "description": "Red-Green-Refactor scaffolding and deterministic unit tests"
    },
    "agent-device": {
        "role": "qa-agent / dev-agent",
        "description": "Callstack mobile automation via semantic accessibility trees (Zero screenshot loops)"
    },
    "playwright": {
        "role": "qa-agent / dev-agent",
        "description": "Isolated browser automation with mandatory try...finally lifecycle"
    },
    "accesslint-scan": {
        "role": "qa-agent",
        "description": "WCAG accessibility and contrast ratio audit"
    },
    "stop-slop": {
        "role": "qa-agent / marketing-agent",
        "description": "Filters out AI clichés, throat-clearing fluff, and passive empty phrasing"
    },
    "ui-ux-pro-max": {
        "role": "design-agent",
        "description": "Design intelligence across 50 styles, 21 palettes, and component specs"
    },
    "apple-design": {
        "role": "design-agent",
        "description": "Apple Human Interface Guidelines (HIG), fluid springs, blur materials, Safe Areas"
    },
    "huashu-design": {
        "role": "design-agent",
        "description": "Spatial hierarchy, weightless depth, glassmorphism, responsive bento grids"
    },
    "systematic-debugging": {
        "role": "debug-agent",
        "description": "Root-cause investigation first before proposing or touching code"
    },
    "surgical-patch": {
        "role": "debug-agent",
        "description": "Narrowest responsible layer bugfix preserving surrounding system behavior"
    },
    "before-you-build": {
        "role": "ba-agent",
        "description": "Product risk, demand evaluation, technical feasibility, and edge cases"
    },
    "writing-plans": {
        "role": "ba-agent",
        "description": "Phased implementation plans with explicit human review gates"
    },
    "avoid-ai-writing": {
        "role": "marketing-agent",
        "description": "Audits and rewrites copy to eliminate 21 predictable AI writing patterns"
    }
}


def audit_recommended_skills(config=None) -> Dict[str, Any]:
    """Audits local IDE skill directories against recommended specialized skills."""
    import os
    from pathlib import Path
    if config is None:
        from .config import get_config
        config = get_config()

    detected_skills = set()
    candidate_dirs = [
        Path.home() / ".gemini" / "config" / "skills",
        Path.home() / ".claude" / "skills",
        Path.home() / ".agents" / "skills",
        Path.home() / ".squad" / "skills",
        config.skills_dir,
    ]
    custom_skills_path = os.environ.get("SQUAD_SKILLS_PATH")
    if custom_skills_path:
        candidate_dirs.append(Path(custom_skills_path))

    for d in candidate_dirs:
        if d and d.exists() and d.is_dir():
            for item in d.iterdir():
                if item.is_dir() and (item / "SKILL.md").exists():
                    detected_skills.add(item.name)
                elif item.is_file() and item.suffix == ".md":
                    detected_skills.add(item.stem)

    installed = {}
    missing = {}
    for skill_name, meta in RECOMMENDED_SKILLS_CATALOG.items():
        if skill_name in detected_skills:
            installed[skill_name] = meta
        else:
            missing[skill_name] = meta

    return {
        "total_recommended": len(RECOMMENDED_SKILLS_CATALOG),
        "installed_count": len(installed),
        "missing_count": len(missing),
        "installed": installed,
        "missing": missing,
        "is_optimal": len(missing) == 0,
        "note": "The recommended skills above are completely OPTIONAL for specialized performance optimization. Squad operates normally even without these skills installed."
    }


def get_skills_for_phase(role: str, phase: Optional[str] = None, platform: str = "web") -> Dict[str, Any]:
    """Returns curated skills matching the role's current phase without polluting context."""
    role_clean = role.lower().replace("-agent", "")
    role_profiles = PHASE_SKILL_PROFILES.get(role_clean, {})
    
    if not phase:
        if role_clean == "dev":
            phase = "coding"
        elif role_clean == "qa":
            phase = f"acceptance_{platform}"
        elif role_clean == "design":
            phase = f"prototyping_{platform}"
        else:
            phase = list(role_profiles.keys())[0] if role_profiles else "default"

    if phase in ["self_test", "self-test"]:
        phase = f"self_test_{platform}"
    elif phase in ["acceptance", "qa"]:
        phase = f"acceptance_{platform}"
    elif phase in ["prototyping", "design"]:
        phase = f"prototyping_{platform}"

    skills = role_profiles.get(phase, [])
    if not skills and role_profiles:
        first_key = list(role_profiles.keys())[0]
        skills = role_profiles[first_key]

    return {
        "role": role_clean,
        "phase": phase,
        "platform": platform,
        "skills": skills,
        "skill_count": len(skills),
        "guidance": f"Load ONLY these {len(skills)} skills for {role_clean} in phase '{phase}'. Avoid dumping full skill catalogs."
    }


def detect_platform(prompt: str = "") -> str:
    """Detect target platform (mobile vs web) via semantic assessment."""
    if not prompt:
        return "web"
    from .semantic_evaluator import evaluate_task_semantics
    sem = evaluate_task_semantics(prompt)
    plat = sem.get("target_platform", "web")
    return "mobile" if plat == "mobile" else "web"


def _heuristic_triage_intent(prompt: str, active_domain: Optional[str] = None) -> Dict[str, Any]:
    """Offline rule-based semantic heuristic triage with cross-keyword disambiguation."""
    from .semantic_evaluator import evaluate_task_semantics
    sem = evaluate_task_semantics(prompt, active_domain=active_domain)
    role = sem["assigned_role"]
    return {
        "role": role,
        "confidence": sem["confidence"],
        "scores": {role: 9.0},
        "provider": sem["provider"]
    }


def triage_intent(prompt: str, active_domain: Optional[str] = None) -> Dict[str, Any]:
    """Classify user prompt into squad role with confidence score using Single-Pass Jev AI."""
    from .semantic_evaluator import evaluate_task_semantics
    sem = evaluate_task_semantics(prompt, active_domain=active_domain)
    role = sem["assigned_role"]
    return {
        "role": role,
        "confidence": sem["confidence"],
        "scores": {role: 9.0},
        "provider": sem["provider"],
        "semantic_assessment": sem
    }



OPTION_SELECTION_PATTERN = re.compile(
    r"\b("
    r"(thực\s*hiện|áp\s*dụng|chọn|triển\s*khai|làm\s*theo|tiến\s*hành|apply|choose|pick|select)\s*"
    r"(phương\s*án|option|cách|giải\s*pháp|hướng|solution|alternative|approach)?\s*"
    r"([0-9]+|[a-eA-E]|một|hai|ba|bốn|năm|one|two|three|1|2|3|4|5)|"
    r"(phương\s*án|option|cách|giải\s*pháp|hướng|solution|alternative|approach)\s*([0-9]+|[a-eA-E]|một|hai|ba|bốn|năm|one|two|three|1|2|3|4|5)"
    r")\b",
    re.IGNORECASE
)


def infer_domain_from_history() -> str:
    """Inspect recent conversation logs and artifacts to determine the active domain when user confirms an option."""
    import json
    from pathlib import Path

    try:
        brain_dir = Path.home() / ".gemini" / "antigravity" / "brain"
        if not brain_dir.exists():
            return "dev"
        conv_dirs = [d for d in brain_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
        conv_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        for d in conv_dirs[:3]:
            t = d / ".system_generated" / "logs" / "transcript.jsonl"
            if not t.exists():
                continue
            lines = t.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
            for line in reversed(lines[-25:]):
                try:
                    data = json.loads(line)
                    for tc in data.get("tool_calls", []):
                        if tc.get("name") == "invoke_subagent":
                            for sub in tc.get("args", {}).get("Subagents", []):
                                tn = sub.get("TypeName", "")
                                for r in ["design", "dev", "debug", "ba", "marketing", "qa"]:
                                    if r in tn:
                                        return r
                    content = data.get("content", "")
                    if content and re.search(r"(phương\s*án|option|lựa\s*chọn)\s*([0-9a-eA-E])", content, re.I):
                        clow = content.lower()
                        if any(k in clow for k in ["ui", "giao diện", "thiết kế", "screen", "màu", "mockup", "style", "css", "layout"]):
                            return "design"
                        if any(k in clow for k in ["marketing", "seo", "copy", "chiến lược", "landing"]):
                            return "marketing"
                        if any(k in clow for k in ["bug", "lỗi", "fix", "crash", "investigate", "stack trace"]):
                            return "debug"
                        if any(k in clow for k in ["code", "implement", "database", "api", "backend", "tính năng", "migration", "service"]):
                            return "dev"
                        if any(k in clow for k in ["test", "nghiệm thu", "kiểm thử", "playwright", "adb"]):
                            return "qa"
                except Exception:
                    pass
    except Exception:
        pass
    return "dev"


def calculate_complexity(prompt: str) -> Dict[str, Any]:
    """Calculate task complexity (1-5) and recommend model tier."""
    text = prompt.lower()
    score = 2
    reasons = []

    words = len(text.split())
    if words > 100:
        score += 1
        reasons.append("long task description")

    if re.search(r"\b(refactor|overhaul|architecture|migration|security|concurrency|distributed|rls|database\s+engine)\b", text):
        score += 2
        reasons.append("high-risk architectural domain")

    if re.search(r"\b(multi-file|system|ecosystem|full-stack|pipeline)\b", text):
        score += 1
        reasons.append("broad architectural scope")

    if re.search(r"\b(typo|rename|format|comment|small|single\s+line|docstring)\b", text):
        score = max(1, score - 2)
        reasons.append("scoped minor change")

    score = max(1, min(5, score))
    tier = "pro" if score >= 3 else "flash"
    tier_label = "Pro (Tier 2)" if score >= 3 else "Flash (Tier 1)"

    return {
        "complexity_score": score,
        "recommended_model": tier,
        "recommended_model_tier": tier_label,
        "reasons": reasons or ["standard single-unit task"],
        "provider": "offline-heuristics"
    }


def score_task_complexity(description: str) -> Dict[str, Any]:
    """Score task complexity using Single-Pass Jev AI or offline heuristics."""
    from .semantic_evaluator import evaluate_task_semantics
    sem = evaluate_task_semantics(description)
    comp_val = sem["complexity_score"]
    tier = sem["recommended_model"]
    tier_label = "Pro (Tier 2)" if comp_val >= 3 else "Flash (Tier 1)"
    return {
        "complexity_score": comp_val,
        "recommended_model": tier,
        "recommended_model_tier": tier_label,
        "confidence": sem["confidence"],
        "provider": sem["provider"],
        "semantic_assessment": sem
    }



def dispatch_task(
    prompt: str,
    active_domain: Optional[str] = None,
    platform: str = "web",
    mode: Optional[str] = None,
    workspace: Optional[str] = None
) -> Dict[str, Any]:
    """Delegates to Unified Squad Gate (SSOT) to guarantee consistent routing with isolated mode support."""
    from .gate import squad_gate
    return squad_gate(prompt, active_domain=active_domain, platform=platform, mode=mode, workspace=workspace)

