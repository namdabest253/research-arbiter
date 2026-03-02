#!/usr/bin/env bash
# Hook script for debate visualizer.
# Reads Claude Code hook JSON from stdin, filters for research/meta agents,
# logs to events.jsonl (persistent), and POSTs to viz server.
# Always exits 0 to never block Claude Code.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/events.jsonl"

INPUT=$(cat)

# Check if this is a research-related event
SHOULD_FORWARD=$(echo "$INPUT" | python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read())
except:
    sys.exit(1)
agent = d.get("agent_type", "") or ""
subagent = (d.get("tool_input") or {}).get("subagent_type", "") or ""
tool = d.get("tool_name", "") or ""
if "research" in agent or "research" in subagent or tool == "Task":
    print("yes")
' 2>/dev/null)

if [ "$SHOULD_FORWARD" = "yes" ]; then
    # Append to persistent log with unix timestamp
    TS=$(date +%s)
    echo "$INPUT" | python3 -c '
import json, sys, os
d = json.loads(sys.stdin.read())
d["_ts"] = int(sys.argv[1])
print(json.dumps(d))
' "$TS" >> "$LOG_FILE" 2>/dev/null

    # POST to viz server (fire-and-forget)
    curl -s -X POST http://localhost:8678/event \
        -H "Content-Type: application/json" \
        -d "$INPUT" >/dev/null 2>&1 &
fi

exit 0
