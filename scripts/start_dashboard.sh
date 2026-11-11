#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
VENV_DIR="${OTBREVIEW_VENV:-.venv}"
PYTHON_BIN="${PYTHON:-python3}"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install -r requirements.txt
exec "$VENV_DIR/bin/python" -m streamlit run dashboard_local/app.py "$@"
