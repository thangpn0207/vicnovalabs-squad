#!/usr/bin/env python3
"""
squad_engine/passive_scanner.py
Tier 0: Passive Scanner Architecture.
Zero-LLM/API cost, pure structural, git diff, lockfile, and AST matching.
Separates detection cost (~0) from execution cost.
"""

import ast
import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple


SIGNAL_GROUPS = {
    "auth_security": [
        "**/auth/**", "**/security/**", "**/middleware/**",
        "**/permissions/**", "**/crypto/**", "**/payment/**",
        "**/payments/**", ".env*", "**/rbac/**"
    ],
    "database": [
        "**/migrations/**", "**/schema/**", "**/*.sql",
        "**/models/**"
    ],
    "ci_cd": [
        ".github/workflows/**", ".gitlab-ci.yml", "Jenkinsfile",
        ".circleci/**", "**/Dockerfile", "docker-compose*.yml",
        "**/*.tf", "**/*.tfvars"
    ],
    "dependency": [
        "package.json", "package-lock.json", "yarn.lock",
        "requirements.txt", "poetry.lock", "Pipfile.lock",
        "go.mod", "go.sum", "Cargo.toml", "Cargo.lock",
        "pom.xml", "build.gradle*"
    ],
    "public_api_surface": []
}

SAFE_PATHS = [
    "**/*.css", "**/*.scss", "**/*.sass", "**/*.less",
    "**/*.md", "**/*.markdown", "**/*.txt",
    "**/assets/**", "**/static/**", "**/i18n/**",
    "**/locales/**", "**/strings/**"
]

NOTICE_TEMPLATES = {
    "auth_security": "💡 Notice: this change touches Auth/Security. Run full squad review? (/squad full, or continue as-is)",
    "database": "💡 Notice: schema/migration change detected. Run squad-qa for migration safety check? (/squad qa)",
    "ci_cd": "💡 Notice: CI/CD or infra config changed. Recommend a pipeline dry-run before merge. (/squad full)",
    "dependency": "💡 Notice: dependency version change detected. Recommend a compatibility check. (/squad qa)",
    "public_api_surface": "💡 Notice: public API surface changed. Run squad-qa for contract verification? (/squad qa)"
}

LOCKFILES = {
    "package-lock.json", "yarn.lock", "poetry.lock",
    "Pipfile.lock", "go.sum", "Cargo.lock"
}


@dataclass
class ScannerResult:
    signals: Dict[str, bool]
    size: Dict[str, int]
    decision: str  # "fast_path" | "notify_only" | "escalate_suggested"
    notice: Optional[str] = None
    files_changed: List[str] = field(default_factory=list)
    file_diff_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signals": self.signals,
            "size": self.size,
            "decision": self.decision,
            "notice": self.notice,
            "files_changed": self.files_changed,
            "reason": self.reason
        }


def _matches_any_glob(path_str: str, globs: List[str]) -> bool:
    normalized = "/" + path_str.replace("\\", "/").strip().lstrip("/")
    raw = path_str.replace("\\", "/").strip()
    basename = Path(raw).name
    for g in globs:
        if fnmatch.fnmatch(raw, g) or fnmatch.fnmatch(normalized, g) or fnmatch.fnmatch(basename, g):
            return True
    return False


def is_safe_path(path_str: str) -> bool:
    return _matches_any_glob(path_str, SAFE_PATHS)


def get_git_diff_name_only(workspace_dir: Optional[str] = None) -> List[str]:
    """Runs `git diff --name-only` and `git status --porcelain` to get all modified files."""
    cwd = workspace_dir or os.getcwd()
    files = set()
    try:
        # Check uncommitted git status
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line[3:].strip().split(" -> ")
                target = parts[-1].strip().strip('"')
                if target:
                    files.add(target)

        # Also check git diff HEAD if available
        r_diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5
        )
        if r_diff.returncode == 0:
            for line in r_diff.stdout.splitlines():
                line = line.strip().strip('"')
                if line:
                    files.add(line)
    except Exception:
        pass
    return sorted(list(files))


def get_git_file_diff_stats(workspace_dir: Optional[str] = None) -> Tuple[Dict[str, Dict[str, int]], int, int]:
    """
    Runs `git diff --numstat` to get added/deleted lines per file and total diff lines.
    Returns (file_stats_dict, total_diff_lines, total_files_changed).
    """
    cwd = workspace_dir or os.getcwd()
    file_stats: Dict[str, Dict[str, int]] = {}
    total_added = 0
    total_deleted = 0

    try:
        r = subprocess.run(
            ["git", "diff", "--numstat", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5
        )
        if r.returncode != 0 or not r.stdout.strip():
            r = subprocess.run(
                ["git", "diff", "--numstat"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5
            )

        if r.returncode == 0:
            for line in r.stdout.splitlines():
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    add_str, del_str, fname = parts[0], parts[1], parts[2]
                    added = int(add_str) if add_str.isdigit() else 0
                    deleted = int(del_str) if del_str.isdigit() else 0
                    total_added += added
                    total_deleted += deleted
                    file_stats[fname] = {"added": added, "deleted": deleted, "total": added + deleted}
    except Exception:
        pass

    total_diff = total_added + total_deleted
    return file_stats, total_diff, len(file_stats)


def detect_ast_public_signature_changes(
    workspace_dir: Optional[str],
    files: List[str]
) -> bool:
    """
    Non-regex AST parser for Python files.
    Compares function/class signatures pre-diff (git show HEAD:file) vs post-diff (current working tree).
    Flags signature_change: true ONLY when an exported/public symbol's parameters, return type,
    or class structure changes. Private functions/classes (starting with '_') are ignored.
    """
    cwd = workspace_dir or os.getcwd()
    # Filter out tests, runners, fixtures, and scratch files from public API surface
    py_files = [
        f for f in files
        if f.endswith(".py")
        and not any(p in f.replace("\\", "/") for p in ["/tests/", "tests/", "/test/", "test/", "test_", "_test.py", "scratch/"])
    ]
    if not py_files:
        return False

    for pf in py_files:
        full_path = Path(cwd) / pf
        if not full_path.exists():
            continue

        # Get pre-diff file content from HEAD
        pre_content = None
        try:
            r = subprocess.run(
                ["git", "show", f"HEAD:{pf}"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5
            )
            if r.returncode == 0:
                pre_content = r.stdout
        except Exception:
            pass

        # If it's a completely new file, check if it exposes public functions
        post_content = None
        try:
            post_content = full_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if pre_content is None:
            # Newly added file has no pre-existing signatures to change
            continue

        # Compare AST definitions between pre and post
        try:
            pre_tree = ast.parse(pre_content)
            post_tree = ast.parse(post_content)

            def extract_signatures(tree: ast.AST) -> Dict[str, Tuple[List[str], Optional[str]]]:
                sigs = {}
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if node.name.startswith("_"):
                            continue
                        args = [a.arg for a in node.args.args]
                        returns = ast.unparse(node.returns) if getattr(node, "returns", None) else None
                        sigs[node.name] = (args, returns)
                    elif isinstance(node, ast.ClassDef):
                        if node.name.startswith("_"):
                            continue
                        # Extract public methods
                        for sub in node.body:
                            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if sub.name.startswith("_") and sub.name != "__init__":
                                    continue
                                args = [a.arg for a in sub.args.args]
                                returns = ast.unparse(sub.returns) if getattr(sub, "returns", None) else None
                                sigs[f"{node.name}.{sub.name}"] = (args, returns)
                return sigs

            pre_sigs = extract_signatures(pre_tree)
            post_sigs = extract_signatures(post_tree)

            # Check if any pre-existing public signature was changed or removed
            for name, (args, returns) in pre_sigs.items():
                if name not in post_sigs:
                    return True  # Removed public symbol
                post_args, post_returns = post_sigs[name]
                if args != post_args or returns != post_returns:
                    return True  # Changed public parameters or return type

        except Exception:
            # Fallback to diff check if AST parse fails (syntax error during edit)
            try:
                r_diff = subprocess.run(
                    ["git", "diff", "-U0", "HEAD", "--", pf],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                for line in r_diff.stdout.splitlines():
                    if line.startswith(("+def ", "+async def ", "+class ", "-def ", "-async def ", "-class ")):
                        parts = line[1:].strip().split()
                        if len(parts) > 1:
                            token = parts[1].split("(")[0].split(":")[0]
                            if token and not token.startswith("_"):
                                return True
            except Exception:
                pass

    return False


def is_patch_version_diff(workspace_dir: Optional[str], file_path: str) -> bool:
    """
    Checks if a dependency file diff is purely a patch-version update (e.g. 1.2.3 -> 1.2.4).
    """
    cwd = workspace_dir or os.getcwd()
    try:
        r = subprocess.run(
            ["git", "diff", "-U0", "HEAD", "--", file_path],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5
        )
        if r.returncode != 0 or not r.stdout.strip():
            r = subprocess.run(
                ["git", "diff", "-U0", "--", file_path],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5
            )
        diff_text = r.stdout
        lines = [line.strip() for line in diff_text.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
        
        # If lockfile only changed slightly (<= 30 lines modified)
        if len(lines) <= 30:
            return True

        # Check semantic version numbers
        old_vers = re.findall(r'"version":\s*"(\d+)\.(\d+)\.(\d+)"', "\n".join([l for l in lines if l.startswith("-")]))
        new_vers = re.findall(r'"version":\s*"(\d+)\.(\d+)\.(\d+)"', "\n".join([l for l in lines if l.startswith("+")]))
        if old_vers and new_vers and len(old_vers) == len(new_vers):
            for (omaj, omin, opat), (nmaj, nmin, npat) in zip(old_vers, new_vers):
                if omaj == nmaj and omin == nmin:
                    return True
    except Exception:
        pass
    return False


def run_passive_scanner(
    workspace_dir: Optional[str] = None,
    touched_files: Optional[List[str]] = None,
    diff_lines_override: Optional[int] = None
) -> ScannerResult:
    """
    Tier 0: Pure deterministic passive scanner.
    Runs on every diff with zero LLM/API calls.
    """
    cwd = workspace_dir or os.getcwd()
    files = touched_files if touched_files is not None else get_git_diff_name_only(cwd)
    file_stats, total_diff_lines, _ = get_git_file_diff_stats(cwd)
    
    if diff_lines_override is not None:
        total_diff_lines = diff_lines_override
    elif touched_files is not None:
        matched_diff = sum(file_stats.get(f, {}).get("total", 0) for f in touched_files)
        total_diff_lines = matched_diff if matched_diff > 0 else (len(touched_files) * 5)
    elif not file_stats and files and total_diff_lines == 0:
        total_diff_lines = len(files) * 5

    files_changed_count = len(files)
    size_info = {
        "files_changed": files_changed_count,
        "total_diff_lines": total_diff_lines
    }

    # Evaluate signals
    signals: Dict[str, bool] = {
        "auth_security": False,
        "database": False,
        "ci_cd": False,
        "dependency": False,
        "public_api_surface": False
    }

    signal_matched_files: Dict[str, List[str]] = {
        k: [] for k in signals.keys()
    }

    for f in files:
        for group in ["auth_security", "database", "ci_cd", "dependency"]:
            if _matches_any_glob(f, SIGNAL_GROUPS[group]):
                signals[group] = True
                signal_matched_files[group].append(f)

    # Public API surface detection
    sig_change = detect_ast_public_signature_changes(cwd, files)
    if sig_change:
        signals["public_api_surface"] = True

    # Check if files are exclusively safe paths (e.g. *.css, *.md, assets)
    all_safe = bool(files) and all(is_safe_path(f) for f in files)

    # Decision Engine Logic:
    # 1. Fast Path:
    # - If no files changed, OR
    # - 100% files are safe paths (*.css, *.md) and no signals active, OR
    # - No signals active AND total_diff_lines <= 50 AND files_changed <= 3
    if not files or all_safe:
        return ScannerResult(
            signals=signals,
            size=size_info,
            decision="fast_path",
            notice=None,
            files_changed=files,
            file_diff_stats=file_stats,
            reason="Files belong exclusively to safe assets/styling/docs or no diff found."
        )

    has_any_signal = any(signals.values())

    if not has_any_signal and total_diff_lines <= 50 and files_changed_count <= 3:
        return ScannerResult(
            signals=signals,
            size=size_info,
            decision="fast_path",
            notice=None,
            files_changed=files,
            file_diff_stats=file_stats,
            reason=f"Small bounded diff ({files_changed_count} files, {total_diff_lines} lines) with zero risk signals."
        )

    # 2. Low Blast Radius Assessment (Notify Only):
    # - A package-lock.json-only diff from a patch-version dependency bump reaches notify_only, not escalate_suggested.
    # - Single CI config typo fix (<= 10 lines diff).
    # - Single database file with <= 5 lines diff (e.g. small comment).
    is_low_blast_radius = False
    active_signals = [k for k, v in signals.items() if v]

    # Check dependency-only change
    if active_signals == ["dependency"]:
        dep_files = signal_matched_files["dependency"]
        only_deps_changed = set(files) == set(dep_files)
        # Lockfile-only or patch version bump or small diff
        if only_deps_changed:
            if all(Path(df).name in LOCKFILES for df in dep_files) or total_diff_lines <= 35:
                is_low_blast_radius = True
            elif any(is_patch_version_diff(cwd, df) for df in dep_files):
                is_low_blast_radius = True

    # Check CI/CD-only small tweak
    elif active_signals == ["ci_cd"]:
        ci_files = signal_matched_files["ci_cd"]
        if set(files) == set(ci_files) and total_diff_lines <= 10:
            is_low_blast_radius = True

    # Check minor DB file tweak
    elif active_signals == ["database"]:
        db_files = signal_matched_files["database"]
        if set(files) == set(db_files) and total_diff_lines <= 5:
            is_low_blast_radius = True

    # Select Primary Notice Template
    primary_signal = None
    for priority_sig in ["auth_security", "database", "ci_cd", "dependency", "public_api_surface"]:
        if signals.get(priority_sig):
            primary_signal = priority_sig
            break

    notice = NOTICE_TEMPLATES.get(primary_signal) if primary_signal else None

    # Decision assignment
    if has_any_signal and is_low_blast_radius:
        # A change touching **/migrations/** always reaches at least notify_only
        return ScannerResult(
            signals=signals,
            size=size_info,
            decision="notify_only",
            notice=notice,
            files_changed=files,
            file_diff_stats=file_stats,
            reason=f"Low blast-radius signal in {primary_signal}."
        )

    if has_any_signal or total_diff_lines > 50 or files_changed_count > 3:
        # If no explicit signal matched but large diff, default to general escalation suggestion
        if not notice:
            notice = "Notice: large multi-file change detected. Run full squad review? (/squad full, or continue as-is)"
        return ScannerResult(
            signals=signals,
            size=size_info,
            decision="escalate_suggested",
            notice=notice,
            files_changed=files,
            file_diff_stats=file_stats,
            reason=f"Risk signal triggered ({primary_signal or 'diff size'}) with high potential blast radius."
        )

    return ScannerResult(
        signals=signals,
        size=size_info,
        decision="fast_path",
        notice=None,
        files_changed=files,
        file_diff_stats=file_stats,
        reason="Default fast-path."
    )
