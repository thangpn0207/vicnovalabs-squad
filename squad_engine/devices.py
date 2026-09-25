#!/usr/bin/env python3
"""
ADB & Physical vs Emulator Device Inspection and Cooperative Hardware Checkpoint.
"""

import os
import sys
import re
import subprocess
from typing import Dict, Any, List


def is_headless_environment() -> bool:
    """Detect if running in a headless CI/CD, container, or server environment."""
    if os.environ.get("HEADLESS") in ["1", "true", "TRUE"]:
        return True
    if os.environ.get("CI") in ["1", "true", "TRUE"]:
        return True
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return True
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return True
    return False



HARDWARE_CONSTRAINED_PATTERN = re.compile(
    r"\b("
    r"p2p|peer[\s\-_]*to[\s\-_]*peer|wi[\s\-_]*fi\s*direct|"
    r"qr|quét\s*mã|scan\s*qr|barcode|camera|chụp\s*ảnh|máy\s*ảnh|"
    r"bluetooth|ble|nfc|"
    r"thiết\s*bị\s*thật|real\s*device|physical\s*device|máy\s*thật|"
    r"web[\s\-_]*socket"
    r")\b",
    re.IGNORECASE
)

RESUME_DEVICE_PATTERN = re.compile(
    r"\b("
    r"đã\s*kết\s*nối|connected|tiếp\s*tục|tiếp|tiếp\s*tục\s*đi|resume|continue|"
    r"đã\s*cắm|đã\s*bật\s*usb|check\s*lại|"
    r"đã\s*quét|đã\s*scan|quét\s*xong|xong\s*rồi|đã\s*xong|done|xong|chạy\s*tiếp"
    r")\b",
    re.IGNORECASE
)


def audit_adb_devices() -> Dict[str, Any]:
    """Inspect connected ADB devices, distinguishing Emulators vs Physical Hardware."""
    emulators = []
    physical_devices = []
    
    try:
        res = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            for line in lines[1:]:
                line = line.strip()
                if not line or "offline" in line or "unauthorized" in line:
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    serial = parts[0]
                    if serial.startswith("emulator-"):
                        emulators.append({"serial": serial, "type": "emulator", "raw": line})
                    else:
                        model = "Android Device"
                        for p in parts[2:]:
                            if p.startswith("model:"):
                                model = p.split(":", 1)[1]
                        physical_devices.append({"serial": serial, "type": "physical", "model": model, "raw": line})
    except Exception:
        pass

    total = len(emulators) + len(physical_devices)
    headless = is_headless_environment()
    if len(physical_devices) > 0 and len(emulators) > 0:
        mode = "dual_device_hybrid"
    elif len(physical_devices) > 1:
        mode = "multi_physical"
    elif len(physical_devices) == 1:
        mode = "single_physical"
    elif len(emulators) > 1:
        mode = "multi_emulator"
    elif len(emulators) == 1:
        mode = "single_emulator"
    elif headless:
        mode = "headless_mock"
    else:
        mode = "no_devices"

    return {
        "status": "success",
        "total_count": total,
        "emulators": emulators,
        "physical_devices": physical_devices,
        "has_emulator": len(emulators) > 0,
        "has_physical_device": len(physical_devices) > 0,
        "is_headless": headless,
        "mode": mode,
        "can_run_single_device": total >= 1 or headless,
        "can_run_dual_device": total >= 2,
        "can_run_physical_camera_qr": len(physical_devices) >= 1 or headless
    }


def is_hardware_constrained(text: str) -> bool:
    """Check if task strictly requires physical hardware interaction via Semantic Evaluator."""
    if not text:
        return False
    from .semantic_evaluator import evaluate_task_semantics
    assessment = evaluate_task_semantics(text)
    return assessment.get("hardware_requirement") == "physical_device_mandatory"



def is_device_resume_prompt(text: str) -> bool:
    """Check if user prompt signals resuming a paused hardware checkpoint."""
    if not text:
        return False
    t = text.strip().lower()
    if t in ["tiếp tục", "tiếp", "resume", "continue", "done", "xong", "đã xong", "ok", "tiếp đi", "chạy tiếp"]:
        return True
    return bool(RESUME_DEVICE_PATTERN.search(t))


def generate_hardware_checkpoint(reason: str, audit_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate interactive Cooperative Hardware Checkpoint message."""
    phys_count = len(audit_data.get("physical_devices", []))
    emu_count = len(audit_data.get("emulators", []))
    
    msg = (
        f"🛑 **[COOPERATIVE HARDWARE CHECKPOINT]**\n"
        f"- **Reason**: {reason}\n"
        f"- **Connected Devices**: {phys_count} physical, {emu_count} emulators.\n"
        f"- **Action Required**:\n"
        f"  1. Connect your physical device via USB cable and enable `USB Debugging`.\n"
        f"  2. Run `adb devices` to verify authorization (status must be `device`, not unauthorized).\n"
        f"  3. Reply with **`continue`** or **`connected`** to resume automated QA verification."
    )
    return {
        "paused": True,
        "checkpoint_type": "HARDWARE_REQUIRED",
        "reason": reason,
        "prompt_message": msg
    }


def run_adb_preflight(serial: str, package_id: str = "", min_storage_mb: int = 500) -> Dict[str, Any]:
    """
    Run ADB preflight checks before starting acceptance testing.

    Verifies:
    1. Device is responsive (adb shell echo __ok__)
    2. App package is installed (if package_id provided)
    3. /data partition has at least min_storage_mb MB free
    4. Screen dimensions are readable (wm size)

    Returns:
        Dict with 'ready' bool, per-check results, and list of 'errors'.
    """
    checks: Dict[str, Any] = {}
    errors: List[str] = []

    # 0. Check device state (online, offline, unauthorized)
    try:
        state_res = subprocess.run(
            ["adb", "-s", serial, "get-state"],
            capture_output=True, text=True, timeout=5
        )
        state_out = state_res.stdout.strip().lower()
        if "offline" in state_out:
            errors.append(f"ADB Error: Device {serial} is offline.")
            return {"serial": serial, "ready": False, "checks": {"device_state": "offline"}, "errors": errors}
        elif "unauthorized" in state_out:
            errors.append(f"ADB Error: Device {serial} is unauthorized. Confirm RSA key fingerprint on device.")
            return {"serial": serial, "ready": False, "checks": {"device_state": "unauthorized"}, "errors": errors}
        elif state_res.returncode != 0:
            errors.append(f"ADB Error: Device {serial} not found or inaccessible: {state_res.stderr.strip()}")
            return {"serial": serial, "ready": False, "checks": {"device_state": "inaccessible"}, "errors": errors}
        checks["device_state"] = state_out or "device"
    except Exception as e:
        errors.append(f"ADB Execution Error on {serial}: {e}")
        return {"serial": serial, "ready": False, "checks": {"device_state": "error"}, "errors": errors}

    def _adb_shell(cmd: str):
        try:
            res = subprocess.run(
                ["adb", "-s", serial, "shell"] + cmd.split(),
                capture_output=True, text=True, timeout=10
            )
            return res.stdout.strip(), res.returncode
        except Exception:
            return "", 1

    # 1. Device responsiveness
    out, rc = _adb_shell("echo __ok__")
    checks["device_responsive"] = rc == 0 and "__ok__" in out
    if not checks["device_responsive"]:
        errors.append(f"Device {serial} not responding to adb shell.")


    # 2. App installation check
    if package_id:
        out, rc = _adb_shell(f"pm list packages")
        installed = package_id in out
        checks["app_installed"] = installed
        checks["package_id"] = package_id
        if not installed:
            errors.append(f"Package '{package_id}' not found on device {serial}. Install APK first.")
    else:
        checks["app_installed"] = None  # Not checked — no package_id given

    # 3. Storage space check
    out, rc = _adb_shell("df /data")
    checks["storage_checked"] = rc == 0
    checks["storage_ok"] = False
    if rc == 0 and out:
        for line in out.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 4:
                try:
                    avail_kb = int(parts[3])
                    avail_mb = avail_kb // 1024
                    checks["storage_available_mb"] = avail_mb
                    checks["storage_ok"] = avail_mb >= min_storage_mb
                    if not checks["storage_ok"]:
                        errors.append(
                            f"Insufficient storage on {serial}: {avail_mb}MB available, "
                            f"{min_storage_mb}MB required."
                        )
                    break
                except (ValueError, IndexError):
                    pass

    # 4. Screen dimensions
    out, rc = _adb_shell("wm size")
    checks["screen_size_readable"] = rc == 0 and "size" in out.lower()
    checks["screen_size"] = out.replace("Physical size:", "").strip() if checks["screen_size_readable"] else None

    return {
        "serial": serial,
        "ready": len(errors) == 0,
        "checks": checks,
        "errors": errors
    }
