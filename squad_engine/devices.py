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

