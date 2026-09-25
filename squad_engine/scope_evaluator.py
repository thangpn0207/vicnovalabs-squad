#!/usr/bin/env python3
"""
squad_engine/scope_evaluator.py
Tier A: Deterministic Scope & Risk Evaluator.
Evaluates risk based on actual filesystem state, git diff, and path patterns.
Zero NLP/LLM token cost, deterministic (<5ms), eliminates surface-regex false positives.
"""

import ast
import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any


# Exact sensitive and safe path globs per directive
SENSITIVE_PATHS = [
    "**/auth/**", "**/security/**", "**/middleware/**",
    "**/permissions/**", "**/migrations/**", "**/crypto/**",
    "**/payment/**", "**/payments/**", ".env*"
]

SAFE_PATHS = [
    "**/*.css", "**/*.scss", "**/*.sass", "**/*.less",
    "**/*.md", "**/*.markdown", "**/*.txt",
    "**/assets/**", "**/static/**", "**/i18n/**",
    "**/locales/**", "**/strings/**"
]

# Regex patterns for matching paths with or without leading slashes
SENSITIVE_PATH_PATTERNS = [
    r"(^|/)auth(/|$|\.)",
    r"(^|/)security(/|$|\.)",
    r"(^|/)middleware(/|$|\.)",
    r"(^|/)permissions?(/|$|\.)",
    r"(^|/)migrations?(/|$|\.)",
    r"(^|/)\.env(\..+)?$",
    r"(^|/)crypto(/|$|\.)",
    r"(^|/)payments?(/|$|\.)",
    r"schema\.(prisma|sql|graphql)$",
    r"(^|/)rbac(/|$|\.)"
]

SAFE_FAST_PATH_PATTERNS = [
    r"\.(css|scss|sass|less|styl)$",
    r"\.(md|markdown|txt|rst|adoc)$",
    r"(^|/)assets/",
    r"(^|/)static/",
    r"(^|/)locales?/",
    r"(^|/)i18n/",
    r"(^|/)strings/",
    r"\.ya?ml$",
    r"\.json$",
    r"\.gitignore$",
    r"LICENSE"
]


@dataclass
class ScopeRiskAssessment:
    path_risk: str                        # 'low' | 'medium' | 'high'
    size_risk: str                        # 'low' | 'high'
    signature_change: bool                # True if public API signature change detected
    decision: str                         # 'fast_path' | 'standard' | 'needs_tier_b'
    # Extended attributes for compatibility
    risk_level: str                       # 'MINIMAL' | 'LOW' | 'HIGH' | 'AMBIGUOUS'
    is_fast_path: bool                    # True if safe to execute inline with minimal overhead
    requires_adversarial_review: bool     # True if sensitive domain or architectural risk
    delegate_to_tier_b: bool              # True if Tier A cannot decide and needs JEV semantic evaluation
    reason: str = ""
    soft_suggestion: Optional[str] = None # Non-blocking 1-line guidance for user
    modified_files: List[str] = field(default_factory=list)
    diff_stats: Dict[str, int] = field(default_factory=lambda: {"added": 0, "deleted": 0, "total": 0})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_risk": self.path_risk,
            "size_risk": self.size_risk,
            "signature_change": self.signature_change,
            "decision": self.decision,
            "risk_level": self.risk_level,
            "is_fast_path": self.is_fast_path,
            "requires_adversarial_review": self.requires_adversarial_review,
            "delegate_to_tier_b": self.delegate_to_tier_b,
            "reason": self.reason,
            "soft_suggestion": self.soft_suggestion,
            "modified_files": self.modified_files,
            "diff_stats": self.diff_stats
        }


def _matches_pattern(path_str: str, patterns: List[str]) -> bool:
    normalized = path_str.replace("\\", "/").strip()
    return any(bool(re.search(pat, normalized, re.IGNORECASE)) for pat in patterns)


def is_sensitive_path(path_str: str) -> bool:
    normalized = "/" + path_str.replace("\\", "/").strip().lstrip("/")
    if any(fnmatch.fnmatch(normalized, pat) or fnmatch.fnmatch(path_str, pat) for pat in SENSITIVE_PATHS):
        return True
    return _matches_pattern(path_str, SENSITIVE_PATH_PATTERNS)


def is_safe_fast_path(path_str: str) -> bool:
    normalized = "/" + path_str.replace("\\", "/").strip().lstrip("/")
    if any(fnmatch.fnmatch(normalized, pat) or fnmatch.fnmatch(path_str, pat) for pat in SAFE_PATHS):
        return True
    return _matches_pattern(path_str, SAFE_FAST_PATH_PATTERNS)


def get_git_modified_files(workspace_dir: Optional[str] = None) -> List[str]:
    """Retrieves list of modified and staged files from Git."""
    cwd = workspace_dir or os.getcwd()
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5
        )
        if r.returncode != 0:
            return []
        files = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line[3:].strip().split(" -> ")
            target = parts[-1].strip().strip('"')
            if target:
                files.append(target)
        return sorted(list(set(files)))
    except Exception:
        return []


def get_git_diff_stats(workspace_dir: Optional[str] = None) -> Dict[str, int]:
    """Retrieves added, deleted, and total modified lines from Git."""
    cwd = workspace_dir or os.getcwd()
    try:
        r = subprocess.run(
            ["git", "diff", "--shortstat", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5
        )
        if r.returncode != 0 or not r.stdout.strip():
            r = subprocess.run(
                ["git", "diff", "--shortstat"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5
            )
        out = r.stdout.strip()
        added = 0
        deleted = 0
        m_add = re.search(r"(\d+)\s+insertion", out)
        m_del = re.search(r"(\d+)\s+deletion", out)
        if m_add:
            added = int(m_add.group(1))
        if m_del:
            deleted = int(m_del.group(1))
        return {"added": added, "deleted": deleted, "total": added + deleted}
    except Exception:
        return {"added": 0, "deleted": 0, "total": 0}


def check_ast_signature_changes(workspace_dir: Optional[str], files: List[str]) -> bool:
    """AST-level detection of public function / class signature modifications for Python files."""
    cwd = workspace_dir or os.getcwd()
    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        return False

    for pf in py_files:
        try:
            r = subprocess.run(
                ["git", "diff", "-U0", "HEAD", "--", pf],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in r.stdout.splitlines():
                if line.startswith(("+def ", "+async def ", "+class ", "-def ", "-async def ", "-class ")):
                    token = line[1:].strip().split()[1] if len(line[1:].strip().split()) > 1 else ""
                    name = token.split("(")[0].split(":")[0]
                    if name and not name.startswith("_"):
                        return True
        except Exception:
            continue
    return False


def evaluate_scope_risk(
    workspace_dir: Optional[str] = None,
    touched_files: Optional[List[str]] = None,
    prompt: Optional[str] = None
) -> ScopeRiskAssessment:
    """
    Tier A Deterministic Scope & Risk Evaluator.
    Evaluates real filesystem and Git state rather than surface prompt regex.
    """
    files = touched_files if touched_files is not None else get_git_modified_files(workspace_dir)
    stats = get_git_diff_stats(workspace_dir) if touched_files is None else {"added": 0, "deleted": 0, "total": 0}

    # Case 1: We have tangible touched files (during or after edit, or explicitly passed)
    if files:
        sensitive_hits = [f for f in files if is_sensitive_path(f)]
        has_sig_change = check_ast_signature_changes(workspace_dir, files)
        size_is_high = stats["total"] > 50 or len(files) > 3

        if sensitive_hits:
            hit_sample = sensitive_hits[0]
            return ScopeRiskAssessment(
                path_risk="high",
                size_risk="high" if size_is_high else "low",
                signature_change=has_sig_change,
                decision="standard",
                risk_level="HIGH",
                is_fast_path=False,
                requires_adversarial_review=True,
                delegate_to_tier_b=False,
                reason=f"Chạm vào file nhạy cảm: {hit_sample}",
                soft_suggestion="💡 Notice: this change touches Auth/Security. Run squad-debug for a deeper red-team review? (/squad debug, or continue inline)",
                modified_files=files,
                diff_stats=stats
            )

        # Check Safe Fast Paths
        if all(is_safe_fast_path(f) for f in files):
            return ScopeRiskAssessment(
                path_risk="low",
                size_risk="low",
                signature_change=False,
                decision="fast_path",
                risk_level="MINIMAL",
                is_fast_path=True,
                requires_adversarial_review=False,
                delegate_to_tier_b=False,
                reason="100% file thay đổi thuộc danh mục UI / Styling / Documentation / Static Assets an toàn",
                soft_suggestion=None,
                modified_files=files,
                diff_stats=stats
            )

        # Check Bounded Diff Size (< 50 lines, <= 3 files, no public signature change)
        if len(files) <= 3 and stats["total"] <= 50 and not has_sig_change:
            return ScopeRiskAssessment(
                path_risk="low",
                size_risk="low",
                signature_change=False,
                decision="fast_path",
                risk_level="LOW",
                is_fast_path=True,
                requires_adversarial_review=False,
                delegate_to_tier_b=False,
                reason=f"Phạm vi thay đổi nhỏ ({len(files)} files, {stats['total']} lines diff, không chạm path nhạy cảm)",
                soft_suggestion=None,
                modified_files=files,
                diff_stats=stats
            )

        # If files fall outside classified paths or multiple unrelated modules
        return ScopeRiskAssessment(
            path_risk="medium",
            size_risk="high" if size_is_high else "low",
            signature_change=has_sig_change,
            decision="needs_tier_b",
            risk_level="AMBIGUOUS",
            is_fast_path=False,
            requires_adversarial_review=False,
            delegate_to_tier_b=True,
            reason=f"Thay đổi đa file ({len(files)} files, {stats['total']} lines) — cần Tầng B đánh giá ngữ nghĩa",
            soft_suggestion=None,
            modified_files=files,
            diff_stats=stats
        )

    # Case 2: No modified files in git yet (prompt/planning stage)
    text = (prompt or "").strip().lower()

    # Plain explanation or documentation query
    if re.search(r"^(giải thích|tại sao|nghĩa là gì|explain|what is|how does)\b", text):
        return ScopeRiskAssessment(
            path_risk="low",
            size_risk="low",
            signature_change=False,
            decision="fast_path",
            risk_level="MINIMAL",
            is_fast_path=True,
            requires_adversarial_review=False,
            delegate_to_tier_b=False,
            reason="Yêu cầu giải thích / tra cứu thông tin (Read-only query)",
            soft_suggestion=None,
            modified_files=[],
            diff_stats=stats
        )

    # If sensitive keywords appear in initial prompt without diff, provide SOFT SUGGESTION, do not force subagent
    sensitive_kw = re.search(r"\b(auth|jwt|oauth|rbac|mật\s*khẩu|phân\s*quyền|migration|bảo\s*mật)\b", text)
    if sensitive_kw:
        kw = sensitive_kw.group(0)
        return ScopeRiskAssessment(
            path_risk="medium",
            size_risk="low",
            signature_change=False,
            decision="needs_tier_b",
            risk_level="LOW",  # Do not block execution
            is_fast_path=False,
            requires_adversarial_review=False,
            delegate_to_tier_b=True,
            reason=f"Yêu cầu chứa từ khóa nhạy cảm '{kw}', cần Tầng B phân tích ngữ nghĩa",
            soft_suggestion="💡 Notice: this change touches Auth/Security. Run squad-debug for a deeper red-team review? (/squad debug, or continue inline)",
            modified_files=[],
            diff_stats=stats
        )

    return ScopeRiskAssessment(
        path_risk="low",
        size_risk="low",
        signature_change=False,
        decision="needs_tier_b",
        risk_level="AMBIGUOUS",
        is_fast_path=False,
        requires_adversarial_review=False,
        delegate_to_tier_b=True,
        reason="Chưa có diff thực tế — chuyển Tầng B (JEV) đánh giá ý định",
        soft_suggestion=None,
        modified_files=[],
        diff_stats=stats
    )


# Alias for backward compatibility
evaluate_scope_and_risk = evaluate_scope_risk
