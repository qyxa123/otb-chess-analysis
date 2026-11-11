#!/usr/bin/env python3
"""Launch the documented Streamlit local dashboard."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    return subprocess.call([sys.executable, "-m", "streamlit", "run",
                            str(ROOT / "dashboard_local" / "app.py"), *sys.argv[1:]], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
