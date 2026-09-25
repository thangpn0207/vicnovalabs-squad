"""
squad_engine/control.py
Interlock Control Bridge for Two-Way Mission Control (Pause, Resume, Kill, Gate Approve/Reject).
"""

import os
import json
import time
import threading
from typing import Dict, List, Optional, Any


class ControlBridge:
    """Manages system execution state and human-in-the-loop control semaphores."""

    DEFAULT_STATE = {
        "global_state": "RUNNING",  # RUNNING | PAUSED | KILLED
        "paused_agents": [],
        "killed_agents": [],
        "gate_decision": "PENDING",  # PENDING | APPROVED | REJECTED
        "gate_notes": "",
        "last_updated": 0.0,
    }

    def __init__(self, state_file: Optional[str] = None):
        self._lock = threading.RLock()
        if state_file is None:
            state_dir = os.path.join(os.getcwd(), ".squad")
            os.makedirs(state_dir, exist_ok=True)
            self.state_file = os.path.join(state_dir, "control_state.json")
        else:
            self.state_file = state_file
            os.makedirs(os.path.dirname(os.path.abspath(state_file)), exist_ok=True)

        self._ensure_state_file()

    def _ensure_state_file(self) -> None:
        with self._lock:
            if not os.path.exists(self.state_file):
                self._save_state(self.DEFAULT_STATE)

    def _load_state(self) -> Dict[str, Any]:
        with self._lock:
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {**self.DEFAULT_STATE, **data}
            except Exception:
                return dict(self.DEFAULT_STATE)

    def _save_state(self, state: Dict[str, Any]) -> None:
        with self._lock:
            state["last_updated"] = time.time()
            tmp_file = f"{self.state_file}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            os.replace(tmp_file, self.state_file)

    def get_state(self) -> Dict[str, Any]:
        """Returns the current control state snapshot."""
        return self._load_state()

    def pause_all(self) -> Dict[str, Any]:
        with self._lock:
            state = self._load_state()
            state["global_state"] = "PAUSED"
            self._save_state(state)
            return state

    def resume_all(self) -> Dict[str, Any]:
        with self._lock:
            state = self._load_state()
            state["global_state"] = "RUNNING"
            state["paused_agents"] = []
            self._save_state(state)
            return state

    def pause_agent(self, role: str) -> Dict[str, Any]:
        with self._lock:
            state = self._load_state()
            paused = set(state.get("paused_agents", []))
            paused.add(role.lower())
            state["paused_agents"] = sorted(list(paused))
            self._save_state(state)
            return state

    def resume_agent(self, role: str) -> Dict[str, Any]:
        with self._lock:
            state = self._load_state()
            paused = set(state.get("paused_agents", []))
            paused.discard(role.lower())
            state["paused_agents"] = sorted(list(paused))
            self._save_state(state)
            return state

    def kill_agent(self, role: str) -> Dict[str, Any]:
        with self._lock:
            state = self._load_state()
            killed = set(state.get("killed_agents", []))
            killed.add(role.lower())
            state["killed_agents"] = sorted(list(killed))
            self._save_state(state)
            return state

    def record_gate_decision(self, decision: str, notes: str = "") -> Dict[str, Any]:
        with self._lock:
            state = self._load_state()
            dec_upper = decision.upper()
            if dec_upper in ["APPROVED", "REJECTED", "PENDING"]:
                state["gate_decision"] = dec_upper
            state["gate_notes"] = notes
            self._save_state(state)
            return state

    def is_paused(self, role: Optional[str] = None) -> bool:
        """Checks if the system or a specific agent role is paused."""
        state = self._load_state()
        if state.get("global_state") == "PAUSED":
            return True
        if role and role.lower() in state.get("paused_agents", []):
            return True
        return False

    def is_killed(self, role: Optional[str] = None) -> bool:
        """Checks if the system or a specific agent role was killed."""
        state = self._load_state()
        if state.get("global_state") == "KILLED":
            return True
        if role and role.lower() in state.get("killed_agents", []):
            return True
        return False

    def reset(self) -> None:
        """Resets control state to default running."""
        with self._lock:
            self._save_state(self.DEFAULT_STATE)
