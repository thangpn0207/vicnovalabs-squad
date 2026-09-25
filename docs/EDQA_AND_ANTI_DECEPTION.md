# 🛡️ Evidence-Driven QA (EDQA) & Anti-Static Deception Guide

> **Target Version**: `v2.1.0`  
> **Core Principle**: *A screen or screenshot that "looks right" is NEVER proof that a feature works. Proof requires empirical runtime state mutation and verified active interaction.*

---

## 1. Why Evidence-Driven QA?

In standard multi-agent systems, agents frequently succumb to **Static Deception**:
- A developer agent claims a task is `DONE` because unit tests pass in-memory with mocked data.
- A QA agent takes a static screenshot of an app screen, notes that the UI looks like the mockup, and immediately stamps `PASS`.
- Unhandled silent runtime exceptions, memory leaks, crashed background daemons, or stale cached data on device pass unnoticed.

**VicnovaLabs Squad v2.1.0** enforces an uncompromising **Bug-Hunter Mindset** where acceptance testing is treated as adversarial verification.

---

## 2. The Acceptance Gate Protocol (POAI)

The **Proof-of-Active-Interaction (POAI)** standard governs all user-facing features:

```
┌──────────────┐                  ┌──────────────┐
│  squad-dev   │                  │   squad-qa   │
└──────┬───────┘                  └──────┬───────┘
       │                                 │
       │ 1. Emits HandoffManifest        │
       │    (with requirement_ids,       │
       │     coverage report >= 85%)     │
       ├────────────────────────────────►│
       │                                 │ 2. Runs ADB / Web Preflight
       │                                 │    (Storage > 500MB, Display, Battery)
       │                                 │
       │                                 │ 3. Generates Batch Test Runner Script
       │                                 │    (Smart Click, Smart Fill, Torture Fuzz)
       │                                 │
       │                                 │ 4. Executes on Host CPU (< 2s)
       │                                 │    (Captures Pre/Post Screenshot, Logs)
       │                                 │
       │                                 │ 5. Validates Evidence Bundle
       │                                 │    - 3-Strategy Mutation Check
       │                                 │    - Anti-False-PASS Gate
       │                                 │    - Logcat Exception Regex Scan
       │                                 │
       │ 6a. DefectTicket (REJECT)       │
       │◄────────────────────────────────┤ (If mutation fails or error detected)
       │                                 │
       │ 6b. SignoffReceipt (DONE)       │
       │◄────────────────────────────────┤ (Only if all POAI criteria verified)
```

---

## 3. The 3 Torture Test Dimensions

Every acceptance verification test must subject inputs and flows to the **3 Torture Dimensions**:

| Dimension | Technique | Expected Resilience |
|---|---|---|
| **1. Boundary & Fuzzing** | `tortureFuzzInput`: SQL injection payloads, 10,000-char strings, UTF-8 emojis (`🔥🚀`), negative numbers, zero, null bytes. | App must sanitize or reject gracefully with user-friendly error banners; never crash or throw unhandled exceptions. |
| **2. State Inversion** | Rapid state toggles: Check $\rightarrow$ Uncheck $\rightarrow$ Re-check; Open modal $\rightarrow$ Cancel $\rightarrow$ Re-open; Add to cart $\rightarrow$ Delete $\rightarrow$ Restore. | State machine must remain consistent without orphaned entities, race conditions, or duplicated UI elements. |
| **3. Latency & Interruption** | Network throttling, offline toggles, backgrounding app and returning. | App must display loading indicators or offline fallbacks; must not freeze main thread or lose input data. |

---

## 4. 3-Strategy Screenshot Mutation Detection

When validating visual evidence across user actions (e.g. before clicking "Submit" vs after clicking "Submit"), `squad validate-evidence` compares pre-action and post-action screenshots using **3 independent strategies**:

1. **Perceptual Difference (`image_diff`)**:
   Uses Python PIL / OpenCV (when available) or pixel-by-pixel luminance comparison. If the perceptual difference is less than 0.5%, the test is flagged as an identical static screenshot.
2. **File Size Delta (`size_delta`)**:
   Compares byte counts between pre-action PNG and post-action PNG. If the file size delta is 0 bytes, compression artifacts did not alter, signaling identical screen state.
3. **Cryptographic SHA256 Hash (`hash`)**:
   Calculates SHA256 hashes of pre and post images. If hashes are identical, mutation is `False`.

> 🚨 **Anti-Deception Rule**: If **NONE** of the 3 strategies detect a delta, the evidence bundle is flagged as **IDENTICAL / UNMUTATED** and the signoff is **REJECTED**.

---

## 5. ADB Hardware Preflight Gate

Before executing mobile tests, the engine runs `squad preflight <serial>`:

```bash
squad preflight emulator-5554 --package com.example.app --min-storage 500
```

**Evaluation Checklist**:
- **Connection**: Device state must be `device` (not `offline` or `unauthorized`).
- **Disk Space**: The `/data` partition must have at least 500MB free. Low disk space causes Android SQLite write failures and false negative test results.
- **Window Manager**: Confirms display resolution (e.g., `1080x2400`) and density.
- **Target Application**: Validates whether the package APK is installed on device.

---

## 6. The Standalone Test Runner Script Pattern

To prevent context window explosion (> 200,000 tokens) caused by step-by-step interactive ADB loops across dozens of chat turns, testing is executed via the **Batch Test Runner Script Pattern**:

1. **Write Once**: Subagent writes a complete test script (`test/squad_runner_xxx.py` or `.js`).
2. **Execute Once**: Invoked via a single `run_command` call (`python3 test/squad_runner_xxx.py`).
3. **Local Assertion Processing**: The runner handles clicks, sleeps, logcat piping, and assertions on the host CPU in milliseconds.
4. **Bounded Output**: The runner produces an evidence directory containing:
   - `run_summary.json`: Process exit code, passed assertions, failed assertions.
   - `pre_action.png` & `post_action.png`: Visual mutation proof.
   - `logcat_filtered.log`: Process-filtered logcat output.

---

## 7. Anti-False-PASS Gate

The Anti-False-PASS Gate ensures that an exit code of 0 is not forged:

```python
# squad_engine/evidence_oracle.py
if summary.get("exit_code") != 0 or summary.get("failed_assertions", 0) > 0:
    return {"valid": False, "errors": ["Test runner reported non-zero exit code or failed assertions"]}
```

Furthermore, `evidence_oracle.py` applies **Strict Multiline Regexes** against all logs:
- Android: `(FATAL EXCEPTION|ANR in|AndroidRuntime: \t*at |NullPointerException|OutOfMemoryError)`
- Web/Node: `(UnhandledPromiseRejection|FATAL ERROR|ReferenceError|TypeError: [^\n]+ is not a function)`
- Python: `(Traceback \(most recent call last\):|AssertionError|RecursionError)`

If any match is detected, the run is rejected automatically, even if the script exited with code 0.
