#!/usr/bin/env python3
import os
import sys
import subprocess
import webbrowser
from pathlib import Path
import time

def main():
    project_root = Path(__file__).resolve().parents[1]
    app_path = project_root / "app.py"
    
    if not app_path.exists():
        print(f"Error: app.py not found at {app_path}")
        sys.exit(1)
        
    print("Starting Chess Analysis Web Interface...")
    
    # Check if streamlit is installed
    try:
        import streamlit
    except ImportError:
        print("Streamlit not found. Installing dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(project_root / "requirements.txt")])
    
    # Run streamlit
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path), *sys.argv[1:]]
    
    print(f"Running: {' '.join(cmd)}")
    
    # Launch in a subprocess
    process = subprocess.Popen(cmd, cwd=project_root)
    
    print("Web server started! It should open in your browser shortly.")
    print("Press Ctrl+C to stop.")
    
    try:
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping server...")
        process.terminate()
        return process.wait()

if __name__ == "__main__":
    raise SystemExit(main())
