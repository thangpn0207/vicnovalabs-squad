#!/usr/bin/env python3
"""
External Anti-Fraud Oracle — Validates acceptance test results
by examining filesystem artifacts (evidence directory), process exit codes,
and bounded runner output. Agent self-reporting is NEVER trusted.

Principle: The oracle reads files and exit codes — it cannot be hallucinated.
"""

import hashlib
import os
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from .stack_detector import StackProfile


# Maximum evidence age before considered stale (5 minutes)
MAX_EVIDENCE_AGE_SECONDS = 300

# Minimum file size to be considered non-placeholder
MIN_EVIDENCE_FILE_SIZE = 100  # bytes

# Minimum screenshot size
MIN_SCREENSHOT_SIZE = 10_000  # 10KB — a real screenshot is typically 50KB+


def validate_evidence_bundle(
    evidence_dir: str,
    stack: Optional[StackProfile] = None,
    max_age_seconds: int = MAX_EVIDENCE_AGE_SECONDS,
    strict_staleness: bool = False,
    strict_mutation: bool = False
) -> Dict[str, Any]:
    """
    Walk evidence directory and validate:
    1. Directory exists and contains files
    2. Screenshot files exist and have plausible sizes (> 10KB)
    3. Pre/post screenshot pairs have different hashes (state mutation proof)
    4. Log files contain no unhandled error signatures
    5. Evidence timestamps are recent (< max_age_seconds)
    """
    edir = Path(evidence_dir)
    errors: List[str] = []
    warnings: List[str] = []
    now = time.time()

    # 1. Directory existence
    if not edir.exists():
        return {
            "valid": False,
            "errors": [f"Evidence directory does not exist: {evidence_dir}"],
            "warnings": [],
            "evidence_files": [],
            "screenshot_pairs": [],
            "mutation_verified": False
        }

    if not edir.is_dir():
        return {
            "valid": False,
            "errors": [f"Evidence path is not a directory: {evidence_dir}"],
            "warnings": [],
            "evidence_files": [],
            "screenshot_pairs": [],
            "mutation_verified": False
        }

    # 2. Enumerate files
    all_files = sorted(edir.rglob("*"))
    evidence_files: List[Dict[str, Any]] = []
    screenshots: List[Path] = []
    log_files: List[Path] = []

    for fp in all_files:
        if not fp.is_file():
            continue

        stat = fp.stat()
        rel = str(fp.relative_to(edir))
        entry: Dict[str, Any] = {
            "path": rel,
            "size_bytes": stat.st_size,
            "age_seconds": round(now - stat.st_mtime, 1)
        }

        # Age check
        if (now - stat.st_mtime) > max_age_seconds:
            entry["stale"] = True
            msg = f"Evidence file is stale ({entry['age_seconds']}s old > max {max_age_seconds}s): {rel}"
            if strict_staleness:
                errors.append(f"EVIDENCE_STALE: {msg}")
            else:
                warnings.append(msg)


        # Categorize
        suffix = fp.suffix.lower()
        if suffix in (".png", ".jpg", ".jpeg", ".webp"):
            screenshots.append(fp)
            if stat.st_size < MIN_SCREENSHOT_SIZE:
                entry["suspicious"] = True
                warnings.append(
                    f"Screenshot suspiciously small ({stat.st_size}B): {rel}"
                )
        elif suffix in (".txt", ".log"):
            log_files.append(fp)

        evidence_files.append(entry)

    if not evidence_files:
        errors.append(f"Evidence directory is empty: {evidence_dir}")

    # 3. Pre/Post Screenshot Pair Mutation Check (P1-C: Flexible naming strategies)
    screenshot_pairs: List[Dict[str, Any]] = []
    mutation_verified = False

    # Strategy A: Canonical squad pattern — step_01_pre.png / step_01_post.png
    pre_posts_a: Dict[str, List[Path]] = {}
    for ss in screenshots:
        match = re.match(r"step_(\d+)_(pre|post)\.", ss.name)
        if match:
            step_id = match.group(1)
            if step_id not in pre_posts_a:
                pre_posts_a[step_id] = []
            pre_posts_a[step_id].append(ss)

    for step_id, files in pre_posts_a.items():
        pre_file = next((f for f in files if "_pre." in f.name), None)
        post_file = next((f for f in files if "_post." in f.name), None)
        if pre_file and post_file:
            pre_hash = hashlib.md5(pre_file.read_bytes()).hexdigest()
            post_hash = hashlib.md5(post_file.read_bytes()).hexdigest()
            mutated = pre_hash != post_hash
            screenshot_pairs.append({
                "step": step_id, "strategy": "canonical",
                "pre": pre_file.name, "post": post_file.name,
                "pre_hash": pre_hash, "post_hash": post_hash, "mutated": mutated
            })
            if not mutated:
                errors.append(
                    f"UI_ACTION_FAILED: Step {step_id} — pre/post screenshots "
                    f"are identical (md5={pre_hash}). No state mutation observed."
                )
            else:
                mutation_verified = True

    # Strategy B: before/after naming — screen_before.png / screen_after.png
    if not screenshot_pairs:
        before_shots = [s for s in screenshots if re.search(r"(?i)(before|_pre\b)", s.stem)]
        after_shots = [s for s in screenshots if re.search(r"(?i)(after|_post\b)", s.stem)]
        if before_shots and after_shots:
            b, a = before_shots[0], after_shots[0]
            bh = hashlib.md5(b.read_bytes()).hexdigest()
            ah = hashlib.md5(a.read_bytes()).hexdigest()
            mutated = bh != ah
            screenshot_pairs.append({
                "step": "before_after", "strategy": "before_after",
                "pre": b.name, "post": a.name,
                "pre_hash": bh, "post_hash": ah, "mutated": mutated
            })
            if mutated:
                mutation_verified = True
            else:
                errors.append(
                    f"UI_ACTION_FAILED: before/after screenshots are identical (md5={bh}). No state mutation observed."
                )

    # Strategy C: Chronological fallback — if ≥2 screenshots with different hashes
    if not screenshot_pairs and len(screenshots) >= 2:
        sorted_shots = sorted(screenshots, key=lambda p: p.stat().st_mtime)
        oldest, newest = sorted_shots[0], sorted_shots[-1]
        oh = hashlib.md5(oldest.read_bytes()).hexdigest()
        nh = hashlib.md5(newest.read_bytes()).hexdigest()
        mutated = oh != nh
        screenshot_pairs.append({
            "step": "chronological", "strategy": "chronological",
            "pre": oldest.name, "post": newest.name,
            "pre_hash": oh, "post_hash": nh, "mutated": mutated
        })
        if mutated:
            mutation_verified = True
        else:
            warnings.append(
                f"Chronological screenshot check: oldest and newest screenshots have identical hash ({oh}). "
                "No visual state change detected across test run."
            )

    # 4. Log file error audit
    error_patterns = [
        r"(?i)unhandled\s*exception",
        r"(?i)fatal\s*error",
        r"(?i)SIGSEGV",
        r"(?i)SIGABRT",
        r"(?i)panic:",
    ]
    if stack and stack.error_signatures:
        error_patterns.extend(stack.error_signatures)

    for lf in log_files:
        try:
            content = lf.read_text(encoding="utf-8", errors="replace")
            for pat in error_patterns:
                matches = re.findall(pat, content)
                if matches:
                    errors.append(
                        f"Error signature in {lf.name}: {matches[:3]}"
                    )
                    break
        except Exception:
            warnings.append(f"Could not read log file: {lf.name}")

    return {
        "valid": len(errors) == 0,
        "evidence_dir": evidence_dir,
        "total_files": len(evidence_files),
        "screenshots": len(screenshots),
        "log_files": len(log_files),
        "evidence_files": evidence_files,
        "screenshot_pairs": screenshot_pairs,
        "mutation_verified": mutation_verified,
        "errors": errors,
        "warnings": warnings
    }


def validate_runner_result(
    runner_output: str,
    exit_code: int,
    stack: Optional[StackProfile] = None
) -> Dict[str, Any]:
    """
    Parse bounded runner output and determine pass/fail:
    - exit_code must be 0
    - No unhandled exceptions in output
    - No RUNNER_EXCEPTION markers
    - Must contain success marker (ALL STEPS PASSED or equivalent)
    """
    errors: List[str] = []
    warnings: List[str] = []

    if exit_code != 0:
        errors.append(f"Runner exited with code {exit_code} (expected 0)")

    # Check for failure markers
    failure_markers = [
        "RUNNER_EXCEPTION:",
        "UI_ACTION_FAILED:",
        "FATAL:",
        "=== FAILURES",
    ]
    for marker in failure_markers:
        if marker in runner_output:
            errors.append(f"Failure marker detected: {marker}")

    # Check for success marker using strict regex (P3-A: tighten false-positive risk)
    success_patterns = [
        r"(?m)^=== ALL STEPS PASSED",                  # Squad mobile/web harness
        r"(?m)^Ran \d+ tests in .+",                   # Python unittest (OK on next line)
        r"(?m)^\d+ passed",                            # pytest summary line
        r"(?m)^ALL STEPS PASSED\b",                    # Squad runner alt format
        r"(?m)^Tests:\s+\d+\s+passed",                 # Jest/vitest
    ]
    # For unittest specifically, the "OK" comes on a separate line after "Ran N tests in Xs"
    unittest_ok = re.search(r"Ran \d+ tests in .+", runner_output) and re.search(r"(?m)^OK\b", runner_output)
    has_success = unittest_ok or any(re.search(pat, runner_output) for pat in success_patterns)

    if not has_success and exit_code == 0:
        warnings.append("Runner exited 0 but no explicit success marker found in output")

    # Stack-specific error detection
    if stack and stack.error_signatures:
        for pat in stack.error_signatures:
            if re.search(pat, runner_output):
                errors.append(f"Stack error signature detected: {pat}")
                break

    return {
        "valid": len(errors) == 0,
        "exit_code": exit_code,
        "has_success_marker": has_success,
        "errors": errors,
        "warnings": warnings,
        "output_lines": len(runner_output.splitlines()),
        "output_truncated": len(runner_output) > 4096
    }
