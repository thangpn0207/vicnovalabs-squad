"""
squad_engine/telemetry.py
Real-time Telemetry Event Bus, Transcript Tailer, and Progress Watcher for Virtual Squad Office.
"""

import os
import json
import time
import queue
import glob
import uuid
import threading
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any, Set


@dataclass
class TelemetryEvent:
    event_type: str
    data: Dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "data": self.data,
        }

    def to_sse_payload(self) -> str:
        """Formats event as a Server-Sent Events (SSE) packet."""
        payload = json.dumps(self.to_dict())
        return f"id: {self.id}\nevent: {self.event_type}\ndata: {payload}\n\n"


class TelemetryEventBus:
    """Thread-safe publish-subscribe event broker for real-time telemetry streaming."""

    def __init__(self, max_history: int = 200):
        self._lock = threading.RLock()
        self.max_history = max_history
        self._history: List[TelemetryEvent] = []
        self._subscribers: Set[queue.Queue] = set()

    def subscribe(self, maxsize: int = 100) -> queue.Queue:
        """Registers a new listener queue."""
        q: queue.Queue = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """Removes a listener queue."""
        with self._lock:
            self._subscribers.discard(q)

    def publish(self, event: TelemetryEvent) -> None:
        """Broadcasts an event to all active subscribers and stores in circular buffer."""
        with self._lock:
            self._history.append(event)
            if len(self._history) > self.max_history:
                self._history.pop(0)

            dead_subs = []
            for sub in self._subscribers:
                try:
                    sub.put_nowait(event)
                except queue.Full:
                    # Drop oldest or mark as dead if subscriber backed up
                    try:
                        sub.get_nowait()
                        sub.put_nowait(event)
                    except Exception:
                        dead_subs.append(sub)
                except Exception:
                    dead_subs.append(sub)

            for d in dead_subs:
                self._subscribers.discard(d)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns recent events up to limit."""
        with self._lock:
            return [e.to_dict() for e in self._history[-limit:]]

    def emit(self, event_type: str, data: Dict[str, Any]) -> TelemetryEvent:
        """Convenience method to create and publish an event."""
        event = TelemetryEvent(event_type=event_type, data=data)
        self.publish(event)
        return event


def extract_tool_call_info(tc: Any) -> Dict[str, Any]:
    """Extracts tool name, arguments, summary, and action from Antigravity or standard tool call representations."""
    if not isinstance(tc, dict):
        return {"name": str(tc), "args": {}, "summary": "", "action": ""}

    name = tc.get("name")
    args = tc.get("args")

    if not name and "call" in tc and isinstance(tc["call"], dict):
        name = tc["call"].get("name")
        args = tc["call"].get("arguments") or tc["call"].get("args")

    if not isinstance(args, dict):
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        else:
            args = {}

    summary = args.get("toolSummary", "")
    action = args.get("toolAction", "")
    return {
        "name": name or "tool",
        "args": args,
        "summary": summary,
        "action": action,
    }


@dataclass
class TranscriptFileState:
    pos: int = 0
    inode: Optional[int] = None
    seen_steps: Set[int] = field(default_factory=set)
    role: str = "dev"
    context_chars: int = 12000
    commands: List[str] = field(default_factory=list)
    tool_call_count: int = 0
    screenshot_count: int = 0
    is_exhausted: bool = False
    is_looping: bool = False


class TranscriptTailer:
    """Background thread that tails active Antigravity transcripts (main conversation + subagents)
    and emits agent activity events, real-time token metrics, loop alerts, and quota depletion events."""

    def __init__(
        self,
        event_bus: TelemetryEventBus,
        transcript_path: Optional[str] = None,
        poll_interval: float = 0.5,
        finops: Optional[Any] = None,
        default_model: str = "gemini-3.0-flash",
    ):
        self.event_bus = event_bus
        self.transcript_path = transcript_path
        self.poll_interval = poll_interval
        self.finops = finops
        self.default_model = default_model
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._file_states: Dict[str, TranscriptFileState] = {}
        self._current_role: str = "dev"

    def discover_transcripts(self) -> List[str]:
        """Auto-discovers active transcript.jsonl files (main conversation + subagents)."""
        if self.transcript_path:
            return [self.transcript_path] if os.path.exists(self.transcript_path) else []

        home = os.path.expanduser("~")
        pattern = os.path.join(
            home, ".gemini", "antigravity", "brain", "*", ".system_generated", "logs", "transcript.jsonl"
        )
        files = glob.glob(pattern)
        if not files:
            return []

        now = time.time()
        scored = []
        for f in files:
            try:
                mt = os.path.getmtime(f)
                if now - mt <= 7200:  # Active in last 2 hours
                    scored.append((mt, f))
            except Exception:
                pass
        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored[:6]] if scored else [files[0]]

    def discover_latest_transcript(self) -> Optional[str]:
        """Backward-compatible discovery of latest transcript."""
        ts = self.discover_transcripts()
        return ts[0] if ts else None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                targets = self.discover_transcripts()
                for target in targets:
                    if target and os.path.exists(target):
                        self._tail_file(target)
            except Exception:
                pass
            time.sleep(self.poll_interval)

    def _tail_file(self, path: str) -> None:
        try:
            stat = os.stat(path)
            state = self._file_states.setdefault(path, TranscriptFileState())

            if state.inode is not None and (state.inode != stat.st_ino or stat.st_size < state.pos):
                state.inode = stat.st_ino
                state.pos = 0
                state.seen_steps.clear()
            elif state.inode is None:
                state.inode = stat.st_ino

            if stat.st_size == state.pos:
                return

            with open(path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(state.pos)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        self._process_entry(path, state, entry)
                    except json.JSONDecodeError:
                        pass
                state.pos = f.tell()
        except Exception:
            pass

    def _detect_role(self, state: TranscriptFileState, entry: Dict[str, Any], path: str) -> str:
        """Determines which agent role is actively executing with multi-stage heuristics."""
        content = entry.get("content", "")
        thinking = entry.get("thinking", "").lower()
        tool_calls = entry.get("tool_calls", [])

        # Check step 0 prompt for subagent role identity
        if entry.get("step_index") == 0 and content:
            c_lower = content.lower()
            for r in ["dev", "qa", "design", "debug", "ba", "marketing"]:
                if f"squad-{r}" in c_lower or f"squad_{r}" in c_lower or f"{r}-agent" in c_lower:
                    state.role = r
                    return r

        # Check tool calls
        for tc in tool_calls:
            t_info = extract_tool_call_info(tc)
            func_name = t_info["name"].lower()
            args = t_info["args"]

            # Check subagent invocation
            subagents = args.get("Subagents", [])
            if subagents and isinstance(subagents, list):
                t_name = (subagents[0].get("TypeName", "") + " " + subagents[0].get("Role", "")).lower()
                for r in ["dev", "qa", "design", "debug", "ba", "marketing"]:
                    if r in t_name:
                        return r

            # Tool-specific heuristics
            if "ui_audit" in func_name or "generate_image" in func_name:
                return "design"
            if "rank_hypotheses" in func_name or "systematic-debugging" in str(args).lower():
                return "debug"
            if "validate-evidence" in str(args).lower() or "device-audit" in str(args).lower() or "audit_adb_devices" in func_name:
                return "qa"
            if "ask_question" in func_name:
                return "ba"

            # File and command heuristics
            fpath = str(args.get("TargetFile") or args.get("AbsolutePath") or "")
            if fpath:
                f_lower = fpath.lower()
                if "test" in f_lower or "tests" in f_lower:
                    return "qa"
                if any(ext in f_lower for ext in [".html", ".css", "mock", "canvas"]):
                    return "design"
                if any(ext in f_lower for ext in [".py", ".dart", ".ts", ".js", ".go", ".rs"]):
                    return "dev"

            cmd = str(args.get("CommandLine") or "").lower()
            if cmd:
                if "unittest" in cmd or "pytest" in cmd or "test" in cmd:
                    return "qa"
                if "git" in cmd or "python" in cmd or "npm" in cmd:
                    return "dev"

        # Thinking keyword heuristics
        if any(w in thinking for w in ["qa", "testing", "assert", "acceptance gate", "signoff"]):
            return "qa"
        if any(w in thinking for w in ["design", "mockup", "easel", "ui/ux", "pixel art"]):
            return "design"
        if any(w in thinking for w in ["root cause", "investigat", "debug-agent", "hypothesis"]):
            return "debug"
        if any(w in thinking for w in ["business analyst", "architecture plan", "rfc", "adr-"]):
            return "ba"
        if any(w in thinking for w in ["marketing", "growth", "cro", "copywriting"]):
            return "marketing"
        if any(w in thinking for w in ["dev-agent", "implement", "refactor", "codebase", "write code"]):
            return "dev"

        return state.role or self._current_role or "dev"

    def _process_entry(self, path: str, state: TranscriptFileState, entry: Dict[str, Any]) -> None:
        step_idx = entry.get("step_index", -1)
        if step_idx in state.seen_steps:
            return
        state.seen_steps.add(step_idx)

        entry_type = entry.get("type", "")
        content = entry.get("content", "")
        thinking = entry.get("thinking", "")
        tool_calls = entry.get("tool_calls", [])

        # Accumulate context characters
        state.context_chars += len(content)

        role = self._detect_role(state, entry, path)
        state.role = role
        self._current_role = role

        # Process tool calls
        if tool_calls:
            for tc in tool_calls:
                t_info = extract_tool_call_info(tc)
                func_name = t_info["name"]
                args = t_info["args"]
                tool_summary = t_info["summary"]
                tool_action = t_info["action"]
                speech = tool_summary or tool_action or f"Running {func_name}..."

                state.tool_call_count += 1
                cmd = str(args.get("CommandLine") or "").strip()
                if cmd:
                    state.commands.append(cmd)
                    if "screencap" in cmd.lower():
                        state.screenshot_count += 1
                elif func_name == "view_file":
                    fpath = str(args.get("AbsolutePath", "")).lower()
                    if any(ext in fpath for ext in [".png", ".jpg", ".jpeg", ".webp"]):
                        state.screenshot_count += 1

                self.event_bus.emit(
                    "TOOL_CALL",
                    {
                        "step_index": step_idx,
                        "role": role,
                        "tool_name": func_name,
                        "tool_summary": tool_summary,
                        "tool_action": tool_action,
                        "speech": speech,
                        "destination": f"desk_{role}",
                        "arguments": {k: str(v)[:200] for k, v in args.items() if k not in ["CodeContent", "ReplacementContent"]},
                    },
                )

        # -------------------------------------------------------------
        # Watchdog: Loop & Runaway Pattern Detection
        # -------------------------------------------------------------
        # 1. Identical Command Repeats (>= 3 repeats)
        if len(state.commands) >= 3 and len(set(state.commands[-3:])) == 1:
            loop_cmd = state.commands[-1]
            if not state.is_looping:
                state.is_looping = True
                self.event_bus.emit(
                    "LOOP_DETECTED",
                    {
                        "step_index": step_idx,
                        "role": role,
                        "error_type": "IDENTICAL_COMMAND_LOOP",
                        "command": loop_cmd,
                        "count": 3,
                        "message": f"Agent {role.upper()} repeated identical command 3 times: '{loop_cmd[:80]}'",
                        "action": "PAUSE_RECOMMENDED",
                    },
                )

        # 2. Screenshot Loop Violation (Rule L.3)
        if state.screenshot_count > 3:
            if not state.is_looping:
                state.is_looping = True
                self.event_bus.emit(
                    "LOOP_DETECTED",
                    {
                        "step_index": step_idx,
                        "role": role,
                        "error_type": "SCREENSHOT_LOOP_VIOLATION",
                        "count": state.screenshot_count,
                        "message": f"Agent {role.upper()} triggered {state.screenshot_count} screenshot operations (limit: 3)!",
                        "action": "PAUSE_RECOMMENDED",
                    },
                )

        # 3. Excessive Tool Call Loop (> 25 calls without completion)
        if state.tool_call_count > 25:
            if not state.is_looping:
                state.is_looping = True
                self.event_bus.emit(
                    "LOOP_DETECTED",
                    {
                        "step_index": step_idx,
                        "role": role,
                        "error_type": "EXCESSIVE_TOOL_CALL_LOOP",
                        "tool_calls": state.tool_call_count,
                        "message": f"Agent {role.upper()} has performed {state.tool_call_count} consecutive tool calls without finishing!",
                        "action": "PAUSE_RECOMMENDED",
                    },
                )

        # -------------------------------------------------------------
        # Watchdog: Quota Depletion & Overworked Agent Detection
        # -------------------------------------------------------------
        # 1. HTTP 429 / RESOURCE_EXHAUSTED detection
        full_text = (str(content) + " " + str(thinking)).lower()
        if any(err_kw in full_text for err_kw in ["resource_exhausted", "429", "quota exceeded", "insufficient_quota"]):
            if not state.is_exhausted:
                state.is_exhausted = True
                self.event_bus.emit(
                    "QUOTA_EXHAUSTED",
                    {
                        "step_index": step_idx,
                        "role": role,
                        "error_type": "RESOURCE_EXHAUSTED_429",
                        "message": f"🚨 QUOTA EXHAUSTED: Agent {role.upper()} hit rate limit (HTTP 429 / RESOURCE_EXHAUSTED)! Squad halted.",
                        "action": "PAUSE_ALL",
                    },
                )

        # -------------------------------------------------------------
        # Real-time Token Recording & FinOps Updates
        # -------------------------------------------------------------
        if entry_type == "PLANNER_RESPONSE" or tool_calls:
            completion_chars = len(thinking) + len(content) + len(json.dumps(tool_calls))
            state.context_chars += completion_chars

            # Approximate tokens (~3.8 chars per token for code & reasoning)
            prompt_tokens = max(120, int(state.context_chars / 3.8))
            completion_tokens = max(60, int(completion_chars / 3.8))
            cached_tokens = int(prompt_tokens * 0.4)

            # Record token burn in FinOps Engine
            if self.finops:
                self.finops.record_usage(
                    agent_role=role,
                    model=self.default_model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cached_tokens=cached_tokens,
                )
                self.event_bus.emit(
                    "TOKEN_USAGE",
                    {
                        "step_index": step_idx,
                        "role": role,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "finops": self.finops.to_dict(),
                    },
                )

                # Budget Hard Limit check immediately after recording spend
                budget_st = self.finops.check_budget()
                if budget_st.get("status") == "HARD_LIMIT":
                    if not state.is_exhausted:
                        state.is_exhausted = True
                        self.event_bus.emit(
                            "QUOTA_EXHAUSTED",
                            {
                                "step_index": step_idx,
                                "role": role,
                                "error_type": "BUDGET_HARD_LIMIT",
                                "current_cost_usd": budget_st.get("current_cost_usd"),
                                "hard_limit_usd": budget_st.get("hard_limit_usd"),
                                "message": f"🚨 BUDGET EXCEEDED: Spend has reached hard limit (${budget_st.get('current_cost_usd', 0):.2f})!",
                                "action": "PAUSE_ALL",
                            },
                        )

        if entry_type == "PLANNER_RESPONSE":
            self.event_bus.emit(
                "AGENT_STATUS",
                {
                    "step_index": step_idx,
                    "role": role,
                    "status": "WORKING",
                    "action": "CODING" if role == "dev" else ("TESTING" if role == "qa" else "THINKING"),
                    "destination": f"desk_{role}",
                    "snippet": thinking[:250] if thinking else f"{role.upper()} is active on current task...",
                    "speech": f"Working on {role.upper()} step #{step_idx}...",
                },
            )


class ProgressWatcher:
    """Monitors PROJECT_PROGRESS.md and broadcasts progress percentages and checklist updates."""

    def __init__(self, event_bus: TelemetryEventBus, progress_path: str = "PROJECT_PROGRESS.md"):
        self.event_bus = event_bus
        self.progress_path = progress_path
        self._last_mtime: float = 0.0

    def parse_progress(self) -> Dict[str, Any]:
        if not os.path.exists(self.progress_path):
            return {"completion_percentage": 0, "completed": [], "ready_for_qa": [], "in_progress": []}

        completed = []
        ready_for_qa = []
        in_progress = []
        total_items = 0

        with open(self.progress_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("- [x]") or stripped.startswith("* [x]"):
                    completed.append(stripped[5:].strip())
                    total_items += 1
                elif "READY_FOR_QA" in stripped or stripped.startswith("- [-]"):
                    ready_for_qa.append(stripped[5:].strip())
                    total_items += 1
                elif "IN_PROGRESS" in stripped:
                    in_progress.append(stripped)

        pct = int(round((len(completed) / max(1, total_items)) * 100)) if total_items > 0 else 0
        return {
            "completion_percentage": pct,
            "total_tasks": total_items,
            "completed_tasks": len(completed),
            "completed": completed,
            "ready_for_qa": ready_for_qa,
            "in_progress": in_progress,
        }

    def check_and_emit(self) -> Optional[Dict[str, Any]]:
        if not os.path.exists(self.progress_path):
            return None
        mtime = os.path.getmtime(self.progress_path)
        if mtime > self._last_mtime:
            self._last_mtime = mtime
            data = self.parse_progress()
            self.event_bus.emit("PROGRESS_UPDATE", data)
            return data
        return None
