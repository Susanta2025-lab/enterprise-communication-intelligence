#!/usr/bin/env bash
set -u
cd /home/home/code/Susanta2025-lab/contextmesh
export PYENV_ROOT="${PYENV_ROOT:-$HOME/.pyenv}"
if [ -d "$PYENV_ROOT" ]; then
  export PATH="$PYENV_ROOT/bin:$PATH"
  eval "$(pyenv init -)"
fi
PY=python3.12
command -v "$PY" >/dev/null 2>&1 || PY=python3
OUT=.phase5-check-results.txt
{
  echo "Python: $($PY --version 2>&1)"
  echo "Which: $(command -v "$PY")"
  echo
  echo "=== pip check ==="
  $PY -m pip check
  echo "EXIT_PIP=$?"
  echo
  echo "=== ruff ==="
  $PY -m ruff check .
  echo "EXIT_RUFF=$?"
  echo
  echo "=== pytest ==="
  $PY -m pytest
  echo "EXIT_PYTEST=$?"
  echo
  echo "=== uvicorn manual verification ==="
  $PY -m uvicorn app.main:app --host 127.0.0.1 --port 8766 &
  UVICORN_PID=$!
  sleep 2
  echo "--- GET /health ---"
  curl -sS http://127.0.0.1:8766/health
  echo
  echo "--- GET /api/v1/health ---"
  curl -sS http://127.0.0.1:8766/api/v1/health
  echo
  echo "--- GET /api/v1/readiness ---"
  curl -sS http://127.0.0.1:8766/api/v1/readiness
  echo
  echo "--- POST /api/v1/communications/analyze ---"
  curl -sS -X POST http://127.0.0.1:8766/api/v1/communications/analyze \
    -H "Content-Type: application/json" \
    -d '{"message":{"body":"Please review the attached report before the deadline.","message_id":"msg-manual-1","metadata":{"source_type":"email","sender":"alice@example.com","recipients":["bob@example.com"],"subject":"Report review"}}}'
  echo
  kill "$UVICORN_PID" 2>/dev/null
  wait "$UVICORN_PID" 2>/dev/null
  echo "EXIT_UVICORN_CHECK=0"
} >"$OUT" 2>&1
cat "$OUT"
