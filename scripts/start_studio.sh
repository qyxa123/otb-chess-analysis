#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${OTBREVIEW_VENV:-.venv}"
PYTHON_BIN="${PYTHON:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.10+ is required. Install Python and rerun this script."
  exit 1
fi
if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install -r requirements.txt

echo "Starting OTBReview Studio on http://localhost:8501"
exec "$VENV_DIR/bin/python" -m streamlit run dashboard/app.py "$@"
