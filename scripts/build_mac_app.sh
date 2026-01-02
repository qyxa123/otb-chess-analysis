#!/usr/bin/env bash
set -e
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "pyinstaller not found. Installing..."
  pip install pyinstaller
fi

APP_ENTRY="$ROOT_DIR/scripts/start_studio.sh"
cat > "$ROOT_DIR/scripts/_studio_launcher.py" <<'PY'
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
subprocess.Popen(["bash", str(ROOT / "scripts/start_studio.sh")])
PY

pyinstaller --name OTBReviewStudio --onefile "$ROOT_DIR/scripts/_studio_launcher.py"
mkdir -p dist
mv dist/OTBReviewStudio "$ROOT_DIR/dist/OTBReviewStudio.app" 2>/dev/null || true
