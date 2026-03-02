#!/usr/bin/env python3
"""Debate Visualizer SSE Server — Python stdlib only.

Endpoints:
  GET  /         → serves debate_viz.html
  GET  /events   → SSE stream (replays recent events on connect)
  GET  /catchup  → JSON array of recent events (for late-joining browsers)
  POST /event    → receives hook JSON, enriches with phase, broadcasts
  POST /replay   → re-reads events.jsonl and broadcasts recent events

On startup, reads events.jsonl to reconstruct state from the current debate
session (events within the last 30 minutes).
"""

import json
import os
import re
import socketserver
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from queue import Queue, Empty
from pathlib import Path

HOST = "0.0.0.0"
PORT = 8678
MAX_HISTORY = 100
CATCHUP_WINDOW_SEC = 30 * 60  # 30 minutes — events older than this are ignored on startup

SCRIPT_DIR = Path(__file__).parent
LOG_FILE = SCRIPT_DIR / "events.jsonl"

# Global state
clients: list[Queue] = []
clients_lock = threading.Lock()
event_history: list[str] = []
history_lock = threading.Lock()


def extract_snippet(text: str, max_len: int = 200) -> str:
    """Extract a meaningful snippet from agent prompt or result text."""
    if not text:
        return ""
    text = text.strip()
    # Remove markdown formatting
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'```[\s\S]*?```', '', text)  # code blocks
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # bold
    text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)  # list bullets
    # Skip pure separator lines
    lines = text.split('\n')
    meaningful = [l.strip() for l in lines if l.strip() and l.strip() != '---']
    result = ' '.join(meaningful)
    # Collapse whitespace
    result = re.sub(r'\s+', ' ', result).strip()
    if len(result) > max_len:
        # Try to cut at sentence boundary
        cut = result[:max_len]
        last_period = cut.rfind('. ')
        last_question = cut.rfind('? ')
        boundary = max(last_period, last_question)
        if boundary > max_len // 2:
            result = cut[:boundary + 1]
        else:
            result = cut.rstrip() + '...'
    return result


def detect_phase(data: dict) -> dict:
    """Enrich event data with detected debate phase."""
    hook_event = data.get("hook_event_name", "")
    agent_type = data.get("agent_type", "") or ""
    tool_input = data.get("tool_input", {}) or {}
    subagent_type = tool_input.get("subagent_type", "") or ""
    prompt = (tool_input.get("prompt", "") or "").lower()
    description = (tool_input.get("description", "") or "").lower()

    phase = None
    label = None

    # Check prompt text for phase keywords
    if prompt:
        if any(k in prompt for k in ["sub-question", "pre-round", "pre_round"]):
            phase, label = "pre_round", "Step 1.5: Identifying Sub-Questions"
        elif any(k in prompt for k in ["round 1", "independent position", "round_1"]):
            phase, label = "round_1", "Round 1 \u2014 Independent Positions"
        elif any(k in prompt for k in ["round 2", "cross-examination", "round_2"]):
            phase, label = "round_2", "Round 2 \u2014 Cross-Examination"
        elif "falsif" in prompt:
            phase, label = "falsification", "Step 5: Falsification"
        elif any(k in prompt for k in ["calibration", "failure probability"]):
            phase, label = "calibration", "Step 5.5: Calibration Probe"

    # Check agent type
    effective_agent = agent_type or subagent_type
    if not phase and "paper-finder" in effective_agent:
        phase, label = "library", "Searching Papers"
    elif not phase and "empiricist" in effective_agent:
        phase, label = "round_1", "Advocate Speaking"
    elif not phase and "theorist" in effective_agent:
        phase, label = "round_1", "Advocate Speaking"
    elif not phase and "contrarian" in effective_agent:
        phase, label = "round_1", "Advocate Speaking"
    elif not phase and "supervisor" in effective_agent:
        phase, label = "supervising", "Supervisor Orchestrating"

    # Determine which agent is active
    active_agent = None
    if "empiricist" in effective_agent:
        active_agent = "empiricist"
    elif "theorist" in effective_agent:
        active_agent = "theorist"
    elif "contrarian" in effective_agent:
        active_agent = "contrarian"
    elif "paper-finder" in effective_agent:
        active_agent = "paper_finder"
    elif "supervisor" in effective_agent:
        active_agent = "supervisor"
    elif "falsif" in effective_agent or (phase == "falsification"):
        active_agent = "falsifier"

    # Determine animation state
    state = "thinking"
    if hook_event == "SubagentStop":
        state = "idle"
    elif hook_event == "SubagentStart":
        state = "speaking"
    elif hook_event == "PreToolUse":
        state = "thinking"  # agent is about to start — show thinking
    elif hook_event == "PostToolUse":
        state = "speaking"  # agent just finished — show what it said

    # Extract text snippet for speech bubbles
    bubble_text = ""
    tool_result = data.get("tool_result", "") or ""
    raw_prompt = tool_input.get("prompt", "") or ""

    if hook_event == "PostToolUse" and tool_result:
        # Agent's actual response — this is what we most want to show
        bubble_text = extract_snippet(str(tool_result), 200)
    elif raw_prompt:
        # The prompt being sent to the agent — shows what it's working on
        bubble_text = extract_snippet(raw_prompt, 200)

    enriched = {
        "timestamp": time.strftime("%H:%M:%S"),
        "hook_event": hook_event,
        "agent_type": effective_agent,
        "active_agent": active_agent,
        "state": state,
        "phase": phase or "unknown",
        "phase_label": label or f"Agent: {effective_agent or 'unknown'}",
        "description": description or tool_input.get("description", ""),
        "bubble_text": bubble_text,
        "is_replay": False,
    }
    return enriched


def broadcast(event_json: str):
    """Send event to all connected SSE clients."""
    with history_lock:
        event_history.append(event_json)
        if len(event_history) > MAX_HISTORY:
            event_history.pop(0)

    dead = []
    with clients_lock:
        for q in clients:
            try:
                q.put_nowait(event_json)
            except Exception:
                dead.append(q)
        for q in dead:
            clients.remove(q)


def load_recent_events():
    """Read events.jsonl and replay recent events to reconstruct state."""
    if not LOG_FILE.exists():
        print("No events.jsonl found — starting fresh.")
        return

    now = time.time()
    cutoff = now - CATCHUP_WINDOW_SEC
    count = 0

    with open(LOG_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = raw.get("_ts", 0)
            if ts < cutoff:
                continue

            enriched = detect_phase(raw)
            enriched["is_replay"] = True
            event_json = json.dumps(enriched)

            with history_lock:
                event_history.append(event_json)
                if len(event_history) > MAX_HISTORY:
                    event_history.pop(0)
            count += 1

    if count:
        print(f"Replayed {count} recent events from events.jsonl")
    else:
        print("No recent events in events.jsonl")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/":
            self.serve_html()
        elif self.path == "/events":
            self.serve_sse()
        elif self.path == "/catchup":
            self.serve_catchup()
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/event":
            self.handle_event()
        elif self.path == "/replay":
            self.handle_replay()
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def serve_html(self):
        html_path = SCRIPT_DIR / "debate_viz.html"
        try:
            content = html_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "debate_viz.html not found")

    def serve_catchup(self):
        """Return current event history as JSON array for late joiners."""
        with history_lock:
            data = "[" + ",".join(event_history) + "]"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data.encode())

    def serve_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = Queue()

        # Replay history to this new client
        with history_lock:
            for evt in event_history:
                try:
                    self.wfile.write(f"data: {evt}\n\n".encode())
                except Exception:
                    return

        with clients_lock:
            clients.append(q)

        try:
            self.wfile.flush()
            while True:
                try:
                    evt = q.get(timeout=15)
                    self.wfile.write(f"data: {evt}\n\n".encode())
                    self.wfile.flush()
                except Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with clients_lock:
                if q in clients:
                    clients.remove(q)

    def handle_event(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
        except Exception:
            self.send_response(400)
            self.end_headers()
            return

        enriched = detect_phase(data)
        event_json = json.dumps(enriched)
        broadcast(event_json)

        agent = enriched.get("active_agent", "?")
        phase = enriched.get("phase_label", "?")
        print(f"[{enriched['timestamp']}] {agent} \u2192 {phase}")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def handle_replay(self):
        """Re-read events.jsonl and broadcast any new recent events."""
        load_recent_events()
        # Broadcast a synthetic "replay_complete" event so the UI knows
        evt = json.dumps({
            "timestamp": time.strftime("%H:%M:%S"),
            "hook_event": "replay_complete",
            "agent_type": "",
            "active_agent": None,
            "state": "idle",
            "phase": "replay",
            "phase_label": "Replay complete",
            "description": "",
            "is_replay": True,
        })
        broadcast(evt)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')


def main():
    print(f"Debate Visualizer on http://{HOST}:{PORT}")
    print(f"Log file: {LOG_FILE}")

    # Replay recent events from disk before accepting connections
    load_recent_events()

    class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
        daemon_threads = True

    server = ThreadedHTTPServer((HOST, PORT), Handler)
    print("Ready — waiting for debate events...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
