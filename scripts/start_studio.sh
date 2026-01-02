#!/usr/bin/env bash
set -e
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d "venv" ]; then
  echo "Creating virtualenv..."
  python3 -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate

pip install -r requirements.txt
pip install -r requirements_dashboard.txt

# Launch Streamlit and open browser
echo "Starting OTBReview Studio on http://localhost:8501"
python -m webbrowser http://localhost:8501 >/dev/null 2>&1 &
exec streamlit run dashboard/app.py
