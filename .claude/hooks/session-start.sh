#!/bin/bash
# SessionStart hook: install Python + UI dependencies so tests and the app
# work out-of-the-box in Claude Code sessions (web and desktop).
set -euo pipefail

cd "$CLAUDE_PROJECT_DIR"

echo "[session-start] Setting up Python environment..."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
./.venv/bin/python -m pip install --upgrade pip >/dev/null
./.venv/bin/python -m pip install -e ".[dev]"

echo "export VIRTUAL_ENV=\"$CLAUDE_PROJECT_DIR/.venv\"" >> "$CLAUDE_ENV_FILE"
echo "export PATH=\"$CLAUDE_PROJECT_DIR/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"

if [ -d "ui" ] && [ -f "ui/package.json" ]; then
  echo "[session-start] Installing UI dependencies..."
  (cd ui && npm install)
fi

echo "[session-start] Done."
