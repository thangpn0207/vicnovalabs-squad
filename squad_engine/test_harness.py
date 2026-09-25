#!/usr/bin/env python3
"""
Test Harness Engine — Thick-Tool, Thin-Prompt.
Generates stack-adaptive standalone test runner scripts and provides
deterministic verification utilities (screenshot hash, filesystem evidence,
exit code oracle). Enforcement lives in executable Python, not prompt text.
"""

import hashlib
import os
import re
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from .stack_detector import StackProfile, STACK_PROFILES


# ---------------------------------------------------------------------------
# 1. Screenshot Mutation Verification
# ---------------------------------------------------------------------------

def verify_screenshot_mutation(pre_path: str, post_path: str) -> Dict[str, Any]:
    """Compare MD5 hashes of pre/post screenshots. Identical == action missed."""
    pre = Path(pre_path)
    post = Path(post_path)
    errors: List[str] = []

    if not pre.exists():
        errors.append(f"Pre-screenshot not found: {pre_path}")
    if not post.exists():
        errors.append(f"Post-screenshot not found: {post_path}")

    if errors:
        return {"mutated": False, "errors": errors}

    pre_hash = hashlib.md5(pre.read_bytes()).hexdigest()
    post_hash = hashlib.md5(post.read_bytes()).hexdigest()
    mutated = pre_hash != post_hash

    result: Dict[str, Any] = {
        "mutated": mutated,
        "pre_hash": pre_hash,
        "post_hash": post_hash,
        "pre_path": pre_path,
        "post_path": post_path,
        "errors": []
    }
    if not mutated:
        result["errors"].append(
            f"UI_ACTION_FAILED: pre and post screenshots are identical "
            f"(md5={pre_hash}). The interaction did not produce a visible state change."
        )
    return result


# ---------------------------------------------------------------------------
# 2. Filesystem Evidence Validation
# ---------------------------------------------------------------------------

def verify_filesystem_evidence(
    evidence_paths: List[str],
    max_age_seconds: int = 300
) -> Dict[str, Any]:
    """Check that evidence files exist, are non-trivial, and are recent."""
    now = time.time()
    checked: List[Dict[str, Any]] = []
    errors: List[str] = []

    for p in evidence_paths:
        fp = Path(p)
        entry: Dict[str, Any] = {"path": p, "exists": fp.exists()}

        if not fp.exists():
            entry["error"] = "File not found"
            errors.append(f"Evidence file missing: {p}")
        else:
            stat = fp.stat()
            entry["size_bytes"] = stat.st_size
            entry["age_seconds"] = round(now - stat.st_mtime, 1)

            if stat.st_size < 100:
                entry["error"] = "File too small (< 100 bytes) — likely empty or placeholder"
                errors.append(f"Evidence file suspiciously small ({stat.st_size}B): {p}")

            if (now - stat.st_mtime) > max_age_seconds:
                entry["error"] = f"File is stale (>{max_age_seconds}s old)"
                errors.append(f"Evidence file stale ({entry['age_seconds']}s): {p}")

        checked.append(entry)

    return {
        "valid": len(errors) == 0,
        "total_files": len(evidence_paths),
        "found_files": sum(1 for c in checked if c["exists"]),
        "files": checked,
        "errors": errors
    }


# ---------------------------------------------------------------------------
# 3. Exit Code Oracle
# ---------------------------------------------------------------------------

def validate_exit_code_evidence(
    exit_code: int,
    stdout: str = "",
    stderr: str = "",
    stack: Optional[StackProfile] = None
) -> Dict[str, Any]:
    """External oracle: accept ONLY if exit_code == 0 AND no error signatures."""
    errors: List[str] = []

    if exit_code != 0:
        errors.append(f"Runner exited with non-zero code: {exit_code}")

    # Check for error signatures in output
    combined = f"{stdout}\n{stderr}"
    error_patterns = [
        r"(?i)unhandled\s*exception",
        r"(?i)fatal\s*error",
        r"(?i)segmentation\s*fault",
        r"(?i)SIGSEGV",
        r"(?i)SIGABRT",
        r"(?i)panic:",
        r"(?i)Traceback \(most recent call last\):",
    ]

    # Add stack-specific patterns
    if stack and stack.error_signatures:
        error_patterns.extend(stack.error_signatures)

    found_errors: List[str] = []
    for pat in error_patterns:
        matches = re.findall(pat, combined)
        if matches:
            found_errors.extend(matches[:2])  # Cap at 2 per pattern

    if found_errors:
        errors.append(
            f"Error signatures detected in runner output: {found_errors[:5]}"
        )

    return {
        "valid": len(errors) == 0,
        "exit_code": exit_code,
        "error_signatures_found": found_errors[:5],
        "errors": errors
    }


# ---------------------------------------------------------------------------
# 3.5 Execution Receipt & Log Compactor (Chặn O(N^2) history growth)
# ---------------------------------------------------------------------------

def compact_execution_log(
    stdout: str,
    stderr: str,
    exit_code: int,
    command: str = "",
    workspace_dir: Optional[str] = None,
    max_summary_lines: int = 5
) -> Dict[str, Any]:
    """
    Saves verbose raw stdout/stderr to disk (/tmp/squad_runs/<timestamp>.log)
    and returns a clean, compact receipt (<= 5 lines) to prevent LLM context explosion.
    """
    log_dir = Path("/tmp/squad_runs")
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cmd_hash = abs(hash(command)) % 10000
    log_file = log_dir / f"run_{ts}_{cmd_hash}.log"

    combined = f"COMMAND: {command}\nEXIT_CODE: {exit_code}\nTIMESTAMP: {ts}\n\n=== STDOUT ===\n{stdout}\n\n=== STDERR ===\n{stderr}"
    log_file.write_text(combined, encoding="utf-8")

    # Generate a compact <= 5 line summary matching exact contract
    combined_clean = (stdout + "\n" + stderr).strip()
    candidates = []
    for line in combined_clean.splitlines():
        l_str = line.strip()
        if re.search(r"\bran \d+ tests?\b", l_str, re.I):
            candidates.insert(0, l_str)
        elif re.search(r"\b(passed|failed|errors?|all steps passed|failures?|ok)\b", l_str, re.I):
            candidates.append(l_str)
    test_summary = candidates[0] if candidates else ""

    if not test_summary:
        non_empty = [l.strip() for l in combined_clean.splitlines() if l.strip()]
        test_summary = non_empty[-1][:100] if non_empty else "Completed"

    status_icon = "✅" if exit_code == 0 else "❌"
    summary_lines = [
        f"{status_icon} [EXECUTION RECEIPT]",
        f"[TEST_RUNNER]: {test_summary} | Exit Code: {exit_code}",
        f"Log saved at: file://{log_file}"
    ]
    if exit_code != 0:
        err_lines = [l.strip() for l in stderr.splitlines() if l.strip()]
        if err_lines:
            summary_lines.append(f"Error summary: {err_lines[-1][:120]}")

    compact_text = "\n".join(summary_lines[:max_summary_lines])

    return {
        "exit_code": exit_code,
        "is_success": exit_code == 0,
        "log_path": str(log_file),
        "compact_summary": compact_text,
        "raw_lines_count": len(combined.splitlines())
    }


# ---------------------------------------------------------------------------
# 4. Stack-Adaptive Test Runner Script Generation
# ---------------------------------------------------------------------------

def _mobile_runner_template(
    package: str,
    device_serial: str,
    steps: List[Dict[str, str]],
    evidence_dir: str
) -> str:
    """Generate a standalone Python ADB test runner script."""
    step_blocks: List[str] = []
    for i, step in enumerate(steps):
        action = step.get("action", "")
        target = step.get("target", "")
        wait_ms = step.get("wait_ms", "2000")

        if action == "launch":
            block = (
                f"# Step {i+1}: Launch app\n"
                f"run(f'adb -s {{DEVICE}} shell am start -n {package}/.MainActivity')\n"
                f"time.sleep(3)\n"
                f"screenshot('{evidence_dir}/step_{i+1:02d}_launch.png')"
            )
        elif action == "tap":
            block = (
                f"# Step {i+1}: Tap {target}\n"
                f"pre = screenshot('{evidence_dir}/step_{i+1:02d}_pre.png')\n"
                f"run(f'adb -s {{DEVICE}} shell input tap {target}')\n"
                f"time.sleep({int(wait_ms)/1000})\n"
                f"post = screenshot('{evidence_dir}/step_{i+1:02d}_post.png')\n"
                f"assert_mutation(pre, post, 'Step {i+1}: tap {target}')"
            )
        elif action == "input_text":
            block = (
                f"# Step {i+1}: Input text\n"
                f"run(f'adb -s {{DEVICE}} shell input text \"{target}\"')\n"
                f"time.sleep(1)\n"
                f"screenshot('{evidence_dir}/step_{i+1:02d}_input.png')"
            )
        elif action == "back":
            block = (
                f"# Step {i+1}: Press Back\n"
                f"run(f'adb -s {{DEVICE}} shell input keyevent KEYCODE_BACK')\n"
                f"time.sleep(1)\n"
                f"screenshot('{evidence_dir}/step_{i+1:02d}_back.png')"
            )
        elif action == "verify_text":
            block = (
                f"# Step {i+1}: Verify text on screen\n"
                f"dump = run(f'adb -s {{DEVICE}} shell uiautomator dump /dev/tty')\n"
                f"assert '{target}' in dump, f'Expected text \"{target}\" not found on screen'\n"
                f"screenshot('{evidence_dir}/step_{i+1:02d}_verify.png')"
            )
        elif action == "logcat_check":
            block = (
                f"# Step {i+1}: Check logcat for errors\n"
                f"logs = run(f'adb -s {{DEVICE}} logcat -d -t 100 | grep -iE \"Error|Exception|Fatal|{package}\"')\n"
                f"with open('{evidence_dir}/logcat_filtered.txt', 'w') as f:\n"
                f"    f.write(logs)"
            )
        else:
            block = (
                f"# Step {i+1}: Custom action: {action}\n"
                f"run(f'adb -s {{DEVICE}} shell {action}')\n"
                f"time.sleep({int(wait_ms)/1000})\n"
                f"screenshot('{evidence_dir}/step_{i+1:02d}_custom.png')"
            )
        step_blocks.append(block)

    joined_steps = "\n\n".join(step_blocks) if step_blocks else "# No explicit steps provided\npass"
    indented_steps = textwrap.indent(joined_steps, "        ")

    return (
        "#!/usr/bin/env python3\n"
        '"""Auto-generated Mobile Test Runner — Squad Test Harness."""\n'
        "import subprocess, sys, os, time, hashlib\n\n"
        f"DEVICE = '{device_serial}'\n"
        f"EVIDENCE_DIR = '{evidence_dir}'\n"
        "ERRORS = []\n\n"
        "os.makedirs(EVIDENCE_DIR, exist_ok=True)\n\n"
        "def run(cmd):\n"
        "    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)\n"
        "    if r.returncode != 0 and r.stderr.strip():\n"
        "        print(f'WARN: {cmd} → rc={r.returncode}', file=sys.stderr)\n"
        "    return r.stdout\n\n"
        "def screenshot(path):\n"
        "    run(f'adb -s {DEVICE} shell screencap -p /sdcard/squad_tmp.png')\n"
        "    run(f'adb -s {DEVICE} pull /sdcard/squad_tmp.png {path}')\n"
        "    return path\n\n"
        "def md5(path):\n"
        "    with open(path, 'rb') as f:\n"
        "        return hashlib.md5(f.read()).hexdigest()\n\n"
        "def assert_mutation(pre, post, label):\n"
        "    h1, h2 = md5(pre), md5(post)\n"
        "    if h1 == h2:\n"
        "        ERRORS.append(f'UI_ACTION_FAILED: {label} — pre==post hash={h1}')\n"
        "        print(f'FAIL: {label} — no UI mutation detected', file=sys.stderr)\n\n"
        "try:\n"
        f"{indented_steps}\n\n"
        "        # Final logcat audit\n"
        "        logs = run(f'adb -s {DEVICE} logcat -d -t 50 | grep -iE \"Error|Exception|Fatal\"')\n"
        "        if logs.strip():\n"
        "            with open(f'{EVIDENCE_DIR}/logcat_errors.txt', 'w') as f:\n"
        "                f.write(logs)\n"
        "            print('WARN: Errors found in logcat (see logcat_errors.txt)')\n\n"
        "except Exception as e:\n"
        "    ERRORS.append(f'RUNNER_EXCEPTION: {e}')\n"
        "    print(f'FATAL: {e}', file=sys.stderr)\n\n"
        "if ERRORS:\n"
        "    print(f'\\n=== FAILURES ({len(ERRORS)}) ===')\n"
        "    for err in ERRORS:\n"
        "        print(f'  ✗ {err}')\n"
        "    sys.exit(1)\n"
        "else:\n"
        "    print('\\n=== ALL STEPS PASSED ===')\n"
        "    print(f'Evidence: {EVIDENCE_DIR}/')\n"
        "    sys.exit(0)\n"
    )


def _web_runner_template(
    url: str,
    steps: List[Dict[str, str]],
    evidence_dir: str
) -> str:
    """Generate a standalone Playwright (Python) test runner script."""
    step_blocks: List[str] = []
    for i, step in enumerate(steps):
        action = step.get("action", "")
        target = step.get("target", "")
        value = step.get("value", "")
        wait_ms = step.get("wait_ms", "2000")

        if action == "navigate":
            block = (
                f"# Step {i+1}: Navigate\n"
                f"page.goto('{target}')\n"
                f"page.wait_for_load_state('networkidle')\n"
                f"page.screenshot(path=f'{{EVIDENCE_DIR}}/step_{i+1:02d}_navigate.png')"
            )
        elif action == "click":
            block = (
                f"# Step {i+1}: Click {target}\n"
                f"page.screenshot(path=f'{{EVIDENCE_DIR}}/step_{i+1:02d}_pre.png')\n"
                f"page.click('{target}')\n"
                f"page.wait_for_timeout({wait_ms})\n"
                f"page.screenshot(path=f'{{EVIDENCE_DIR}}/step_{i+1:02d}_post.png')"
            )
        elif action == "fill":
            block = (
                f"# Step {i+1}: Fill {target}\n"
                f"page.fill('{target}', '{value}')\n"
                f"page.wait_for_timeout(500)\n"
                f"page.screenshot(path=f'{{EVIDENCE_DIR}}/step_{i+1:02d}_fill.png')"
            )
        elif action == "assert_text":
            block = (
                f"# Step {i+1}: Assert text visible\n"
                f"assert page.is_visible('text={target}'), f'Expected text \"{target}\" not visible'\n"
                f"page.screenshot(path=f'{{EVIDENCE_DIR}}/step_{i+1:02d}_assert.png')"
            )
        elif action == "assert_url":
            block = (
                f"# Step {i+1}: Assert URL\n"
                f"assert '{target}' in page.url, f'Expected URL to contain \"{target}\", got {{page.url}}'"
            )
        else:
            block = (
                f"# Step {i+1}: Custom {action}\n"
                f"page.{action}('{target}')\n"
                f"page.wait_for_timeout({wait_ms})\n"
                f"page.screenshot(path=f'{{EVIDENCE_DIR}}/step_{i+1:02d}_custom.png')"
            )
        step_blocks.append(block)

    joined_steps = "\n\n".join(step_blocks) if step_blocks else "# No explicit steps provided\npass"
    indented_steps = textwrap.indent(joined_steps, "    ")

    return (
        "#!/usr/bin/env python3\n"
        '"""Auto-generated Web Test Runner — Squad Test Harness."""\n'
        "import sys, os, hashlib\n\n"
        f"EVIDENCE_DIR = '{evidence_dir}'\n"
        "ERRORS = []\n"
        "os.makedirs(EVIDENCE_DIR, exist_ok=True)\n\n"
        "try:\n"
        "    from playwright.sync_api import sync_playwright\n"
        "except ImportError:\n"
        "    print('FATAL: playwright not installed. Run: pip install playwright && playwright install chromium')\n"
        "    sys.exit(1)\n\n"
        "browser = None\n"
        "try:\n"
        "    pw = sync_playwright().start()\n"
        "    browser = pw.chromium.launch(\n"
        "        headless=True,\n"
        "        args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']\n"
        "    )\n"
        "    page = browser.new_page()\n\n"
        "    console_errors = []\n"
        "    page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)\n"
        "    page.on('pageerror', lambda exc: console_errors.append(str(exc)))\n\n"
        f"{indented_steps}\n\n"
        "    # Console error audit\n"
        "    if console_errors:\n"
        "        with open(f'{EVIDENCE_DIR}/console_errors.txt', 'w') as f:\n"
        "            f.write('\\n'.join(console_errors[:20]))\n"
        "        print(f'WARN: {len(console_errors)} console errors detected')\n\n"
        "except Exception as e:\n"
        "    ERRORS.append(f'RUNNER_EXCEPTION: {e}')\n"
        "    print(f'FATAL: {e}', file=sys.stderr)\n"
        "finally:\n"
        "    if browser:\n"
        "        browser.close()\n"
        "        browser = None\n\n"
        "if ERRORS:\n"
        "    print(f'\\n=== FAILURES ({len(ERRORS)}) ===')\n"
        "    for err in ERRORS:\n"
        "        print(f'  ✗ {err}')\n"
        "    sys.exit(1)\n"
        "else:\n"
        "    print('\\n=== ALL STEPS PASSED ===')\n"
        "    print(f'Evidence: {EVIDENCE_DIR}/')\n"
        "    sys.exit(0)\n"
    )


def _backend_runner_template(
    test_command: str,
    evidence_dir: str
) -> str:
    """Generate a standalone backend test runner wrapper."""
    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Auto-generated Backend Test Runner — Squad Test Harness.\"\"\"
        import subprocess, sys, os

        EVIDENCE_DIR = '{evidence_dir}'
        os.makedirs(EVIDENCE_DIR, exist_ok=True)

        print(f'Running: {test_command}')
        result = subprocess.run(
            '{test_command}',
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )

        # Write bounded output
        with open(f'{{EVIDENCE_DIR}}/test_stdout.txt', 'w') as f:
            f.write(result.stdout[-4096:])
        with open(f'{{EVIDENCE_DIR}}/test_stderr.txt', 'w') as f:
            f.write(result.stderr[-4096:])

        # Print bounded summary
        lines = result.stdout.strip().splitlines()
        if len(lines) > 40:
            print('\\n'.join(lines[:5]))
            print(f'... ({{len(lines) - 10}} lines truncated, full output in {{EVIDENCE_DIR}}/test_stdout.txt)')
            print('\\n'.join(lines[-5:]))
        else:
            print(result.stdout)

        if result.stderr.strip():
            err_lines = result.stderr.strip().splitlines()
            for line in err_lines[-10:]:
                print(f'STDERR: {{line}}', file=sys.stderr)

        sys.exit(result.returncode)
    """)


def generate_test_runner_script(
    stack: StackProfile,
    journey_steps: List[Dict[str, str]],
    evidence_dir: str,
    package: str = "",
    device_serial: str = "emulator-5554",
    url: str = "http://localhost:3000",
    output_dir: str = "test"
) -> Dict[str, Any]:
    """
    Generate a standalone test runner script adapted to the detected stack.

    P2-D: Automatically writes the script to disk (output_dir/filename) to
    prevent the 'ghost verification_command' problem where the script content
    is returned but never written to the filesystem.

    Args:
        stack: Detected project stack profile.
        journey_steps: Ordered list of test steps (action, target, value).
        evidence_dir: Directory to write screenshots and logs.
        package: Android package ID for mobile runners.
        device_serial: ADB device serial for mobile runners.
        url: Base URL for web runners.
        output_dir: Directory to write the generated runner script (default 'test/').
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    evidence_dir = evidence_dir or f"/tmp/squad-evidence-{ts}"

    if stack.category == "mobile":
        script = _mobile_runner_template(
            package=package,
            device_serial=device_serial,
            steps=journey_steps,
            evidence_dir=evidence_dir
        )
        filename = f"squad_runner_mobile_{ts}.py"
    elif stack.category == "web":
        script = _web_runner_template(
            url=url,
            steps=journey_steps,
            evidence_dir=evidence_dir
        )
        filename = f"squad_runner_web_{ts}.py"
    else:
        script = _backend_runner_template(
            test_command=stack.test_runner,
            evidence_dir=evidence_dir
        )
        filename = f"squad_runner_backend_{ts}.py"

    # P2-D: Auto-write script to output_dir — prevents ghost verification_command
    script_path: Optional[str] = None
    write_error: Optional[str] = None
    try:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        script_file = out_path / filename
        script_file.write_text(script, encoding="utf-8")
        script_path = str(script_file.resolve())
    except Exception as e:
        write_error = str(e)

    return {
        "script_content": script,
        "filename": filename,
        "script_path": script_path,
        "write_error": write_error,
        "evidence_dir": evidence_dir,
        "stack": stack.stack_id,
        "execution_command": f"python3 {script_path or filename}"
    }



def generate_mobile_runner(
    package: str,
    device_serial: str,
    steps: List[Dict[str, str]],
    evidence_dir: str = ""
) -> str:
    """Convenience: generate mobile runner script content."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not evidence_dir:
        evidence_dir = f"/tmp/squad-evidence-{ts}"
    return _mobile_runner_template(package, device_serial, steps, evidence_dir)


def generate_web_runner(
    url: str,
    steps: List[Dict[str, str]],
    evidence_dir: str = ""
) -> str:
    """Convenience: generate web (Playwright) runner script content."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not evidence_dir:
        evidence_dir = f"/tmp/squad-evidence-{ts}"
    return _web_runner_template(url, steps, evidence_dir)
