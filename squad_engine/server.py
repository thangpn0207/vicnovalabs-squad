"""
squad_engine/server.py
Zero-Dependency Python HTTP & SSE Telemetry Server for VicnovaLabs Squad Virtual Office.
"""

import os
import sys
import json
import time
import socket
import secrets
import webbrowser
import threading
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict, Any

from squad_engine.finops import FinOpsEngine
from squad_engine.telemetry import TelemetryEventBus, TelemetryEvent, TranscriptTailer, ProgressWatcher
from squad_engine.control import ControlBridge


def get_or_create_session_token() -> str:
    """Retrieves or generates a secure local session authentication token."""
    squad_dir = os.path.join(os.path.expanduser("~"), ".squad")
    os.makedirs(squad_dir, exist_ok=True)
    token_file = os.path.join(squad_dir, "session.token")

    if os.path.exists(token_file):
        try:
            with open(token_file, "r", encoding="utf-8") as f:
                token = f.read().strip()
                if len(token) >= 16:
                    return token
        except Exception:
            pass

    token = secrets.token_hex(16)
    try:
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(token)
    except Exception:
        pass
    return token


def find_available_port(start_port: int = 7777, max_attempts: int = 10, host: str = "127.0.0.1") -> int:
    """Finds the first available port starting from start_port."""
    for p in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return start_port


class SquadOfficeHandler(BaseHTTPRequestHandler):
    """HTTP request handler serving static dashboard assets, SSE stream, and control RPCs."""

    server_instance: "SquadOfficeServer" = None  # Injected by server

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy default HTTP logging
        pass

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Squad-Token")

    def _validate_auth(self, parsed_url) -> bool:
        """Validates the local session token via header or query parameter."""
        expected = self.server_instance.session_token
        # Check header
        token_hdr = self.headers.get("X-Squad-Token")
        if token_hdr and token_hdr == expected:
            return True
        # Check query params
        qs = parse_qs(parsed_url.query)
        token_qs = qs.get("token", [None])[0]
        if token_qs and token_qs == expected:
            return True
        return False

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. API: Server Status Snapshot
        if path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            payload = {
                "status": "online",
                "port": self.server_instance.port,
                "uptime": round(time.time() - self.server_instance.start_time, 1),
                "finops": self.server_instance.finops.to_dict(),
                "control": self.server_instance.control.get_state(),
                "progress": self.server_instance.progress_watcher.parse_progress(),
                "recent_events": self.server_instance.event_bus.get_history(limit=20),
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        # 2. API: SSE Streaming
        if path == "/api/stream":
            if not self._validate_auth(parsed):
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Forbidden: Invalid or missing X-Squad-Token"}).encode("utf-8"))
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self._send_cors_headers()
            self.end_headers()

            # Subscribe to event bus
            sub_queue = self.server_instance.event_bus.subscribe()

            # Send initial state event
            init_event = TelemetryEvent(
                event_type="INIT_STATE",
                data={
                    "finops": self.server_instance.finops.to_dict(),
                    "control": self.server_instance.control.get_state(),
                    "progress": self.server_instance.progress_watcher.parse_progress(),
                },
            )
            self.wfile.write(init_event.to_sse_payload().encode("utf-8"))
            self.wfile.flush()

            try:
                while self.server_instance.running:
                    try:
                        event = sub_queue.get(timeout=2.0)
                        self.wfile.write(event.to_sse_payload().encode("utf-8"))
                        self.wfile.flush()
                    except Exception:
                        # Timeout, send heartbeat keepalive
                        hb = TelemetryEvent(event_type="HEARTBEAT", data={"time": time.time()})
                        self.wfile.write(hb.to_sse_payload().encode("utf-8"))
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                self.server_instance.event_bus.unsubscribe(sub_queue)
            return

        # 3. Static Web App Assets Serving
        web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
        if path in ["", "/"]:
            file_name = "index.html"
        else:
            file_name = path.lstrip("/")

        file_path = os.path.join(web_dir, file_name)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            content_type = "text/plain"
            if file_name.endswith(".html"):
                content_type = "text/html; charset=utf-8"
            elif file_name.endswith(".css"):
                content_type = "text/css; charset=utf-8"
            elif file_name.endswith(".js"):
                content_type = "application/javascript; charset=utf-8"
            elif file_name.endswith(".json"):
                content_type = "application/json"
            elif file_name.endswith(".png"):
                content_type = "image/png"
            elif file_name.endswith(".svg"):
                content_type = "image/svg+xml"

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self._send_cors_headers()
            self.end_headers()
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())
            return

        # 4. Fallback 404
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if not self._validate_auth(parsed):
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Forbidden: Invalid or missing X-Squad-Token"}).encode("utf-8"))
            return

        # Read JSON body
        content_length = int(self.headers.get("Content-Length", 0))
        body = {}
        if content_length > 0:
            try:
                body_bytes = self.rfile.read(content_length)
                body = json.loads(body_bytes.decode("utf-8"))
            except Exception:
                body = {}

        # 1. Control: Pause
        if path == "/api/control/pause":
            role = body.get("role")
            if role:
                st = self.server_instance.control.pause_agent(role)
            else:
                st = self.server_instance.control.pause_all()
            self.server_instance.event_bus.emit("CONTROL_CHANGE", {"action": "PAUSE", "state": st})
            self._json_response(200, {"success": True, "state": st})
            return

        # 2. Control: Resume
        if path == "/api/control/resume":
            role = body.get("role")
            if role:
                st = self.server_instance.control.resume_agent(role)
            else:
                st = self.server_instance.control.resume_all()
            self.server_instance.event_bus.emit("CONTROL_CHANGE", {"action": "RESUME", "state": st})
            self._json_response(200, {"success": True, "state": st})
            return

        # 3. Control: Kill
        if path == "/api/control/kill":
            role = body.get("role", "all")
            st = self.server_instance.control.kill_agent(role)
            self.server_instance.event_bus.emit("CONTROL_CHANGE", {"action": "KILL", "role": role, "state": st})
            self._json_response(200, {"success": True, "state": st})
            return

        # 4. Gate: Decision (Approve / Reject)
        if path == "/api/gate/decision":
            decision = body.get("decision", "APPROVED")
            notes = body.get("notes", "")
            st = self.server_instance.control.record_gate_decision(decision, notes)
            self.server_instance.event_bus.emit("GATE_EVENT", {"decision": decision, "notes": notes, "state": st})
            self._json_response(200, {"success": True, "state": st})
            return

        # 5. External Telemetry Event Ingestion
        if path == "/api/telemetry/event":
            event_type = body.get("event_type", "CUSTOM")
            data = body.get("data", {})
            event = self.server_instance.event_bus.emit(event_type, data)
            self._json_response(200, {"success": True, "event_id": event.id})
            return

        self._json_response(404, {"error": "Not Found"})

    def _json_response(self, code: int, payload: Dict[str, Any]) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))


class SquadOfficeServer:
    """Manages the lifecycle of the Virtual Squad Office server and companion monitors."""

    def __init__(
        self,
        port: int = 7777,
        host: str = "127.0.0.1",
        session_token: Optional[str] = None,
        state_file: Optional[str] = None,
        progress_path: str = "PROJECT_PROGRESS.md",
    ):
        self.host = host
        self.requested_port = port
        self.port = find_available_port(start_port=port, host=host)
        self.session_token = session_token or get_or_create_session_token()
        self.start_time = time.time()
        self.running = False

        self.finops = FinOpsEngine()
        self.event_bus = TelemetryEventBus()
        self.control = ControlBridge(state_file=state_file)
        self.progress_watcher = ProgressWatcher(self.event_bus, progress_path=progress_path)
        self.transcript_tailer = TranscriptTailer(self.event_bus, finops=self.finops)

        self._httpd: Optional[ThreadingHTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None

    def start(self, open_browser_tab: bool = False) -> str:
        """Starts the server in a background thread and returns the access URL."""
        if self.running:
            return self.get_url()

        SquadOfficeHandler.server_instance = self
        self._httpd = ThreadingHTTPServer((self.host, self.port), SquadOfficeHandler)
        self.running = True

        self._server_thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._server_thread.start()

        # Start companion watchers
        self.transcript_tailer.start()

        url = self.get_url()
        self._write_pid_file()

        if open_browser_tab:
            try:
                webbrowser.open(url)
            except Exception:
                pass

        return url

    def stop(self) -> None:
        """Gracefully terminates the server and background watchers."""
        self.running = False
        self.transcript_tailer.stop()
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        self._remove_pid_file()

    def get_url(self) -> str:
        return f"http://{self.host}:{self.port}/?token={self.session_token}"

    def _write_pid_file(self) -> None:
        squad_dir = os.path.join(os.getcwd(), ".squad")
        os.makedirs(squad_dir, exist_ok=True)
        pid_file = os.path.join(squad_dir, "office.pid")
        try:
            with open(pid_file, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "port": self.port, "token": self.session_token, "url": self.get_url()}, f)
        except Exception:
            pass

    def _remove_pid_file(self) -> None:
        pid_file = os.path.join(os.getcwd(), ".squad", "office.pid")
        if os.path.exists(pid_file):
            try:
                os.remove(pid_file)
            except Exception:
                pass
