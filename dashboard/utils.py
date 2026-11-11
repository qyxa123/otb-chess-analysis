from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_OUTDIR = PROJECT_ROOT / "out" / "runs"


def ensure_outdir() -> Path:
    BASE_OUTDIR.mkdir(parents=True, exist_ok=True)
    return BASE_OUTDIR


def create_run_dir() -> Tuple[Path, str]:
    ensure_outdir()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = BASE_OUTDIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir, run_id


def save_uploaded_file(uploaded_file, run_dir: Path) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".mp4"
    dest = run_dir / f"input_video{suffix}"
    with dest.open("wb") as f:
        f.write(uploaded_file.getbuffer())
    return dest


class ProcessLogStream:
    """Iterable logs with an exit status available after iteration completes."""

    def __init__(self, command: List[str], cwd: Optional[Path] = None):
        self.process = subprocess.Popen(
            command, cwd=str(cwd or PROJECT_ROOT), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        self.returncode: Optional[int] = None

    def __iter__(self) -> Generator[str, None, None]:
        try:
            if self.process.stdout:
                for line in self.process.stdout:
                    yield line.rstrip("\n")
        finally:
            if self.process.stdout:
                self.process.stdout.close()
            self.returncode = self.process.wait()


def stream_process(command: List[str], cwd: Optional[Path] = None) -> ProcessLogStream:
    return ProcessLogStream(command, cwd)


def analysis_command(input_path: Path, run_dir: Path, *, use_piece_tags: bool,
                     fps: float, motion_threshold: float, stable_duration: float = 0.7,
                     tag_sensitivity: float = 1.0, enable_clahe: bool = True,
                     enable_threshold: bool = True) -> List[str]:
    command = [
        sys.executable, "-u", "-m", "otbreview", "analyze",
        "--input", str(input_path.resolve()), "--outdir", str(run_dir.resolve()),
        "--use_markers", "1", "--use-piece-tags", str(int(use_piece_tags)),
        "--fps", str(fps), "--motion-threshold", str(motion_threshold),
        "--stable-duration", str(stable_duration), "--tag-sensitivity", str(tag_sensitivity),
    ]
    if not enable_clahe:
        command.append("--disable-clahe")
    if not enable_threshold:
        command.append("--disable-threshold-path")
    return command


def write_run_metadata(run_dir: Path, data: Dict) -> None:
    meta_path = run_dir / "run_meta.json"
    try:
        meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_run_metadata(run_dir: Path) -> Dict:
    meta_path = run_dir / "run_meta.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def discover_runs() -> List[Tuple[str, Path]]:
    ensure_outdir()
    runs: List[Tuple[str, Path]] = []
    for child in BASE_OUTDIR.iterdir():
        if child.is_dir():
            runs.append((child.name, child))
    runs.sort(reverse=True)
    return runs


def find_first_image(directory: Path) -> Optional[Path]:
    if not directory.exists():
        return None
    for pattern in ("*.png", "*.jpg", "*.jpeg"):
        matches = sorted(directory.glob(pattern))
        if matches:
            return matches[0]
    return None


def key_artifacts(run_dir: Path) -> Dict[str, Optional[Path]]:
    debug_dir = run_dir / "debug"
    overlays_dir = debug_dir / "tag_overlays"
    tag_overlay = debug_dir / "tag_overlay_0001.png"
    if not tag_overlay.exists():
        first_overlay = find_first_image(overlays_dir)
        tag_overlay = first_overlay if first_overlay else None

    return {
        "stable": find_first_image(debug_dir / "stable_frames"),
        "warped": find_first_image(debug_dir / "warped_boards"),
        "tag_overlay": tag_overlay if tag_overlay and tag_overlay.exists() else None,
        "grid": debug_dir / "grid_overlay.png" if (debug_dir / "grid_overlay.png").exists() else None,
    }


def load_board_grid(board_path: Path) -> Optional[List[List[int]]]:
    if not board_path.exists():
        return None
    try:
        data = json.loads(board_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    sequences = _board_sequences(data)
    return sequences[0] if sequences else None


def load_board_sequences(board_path: Path) -> List[List[List[int]]]:
    if not board_path.exists():
        return []
    try:
        data = json.loads(board_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return _board_sequences(data)


def _board_sequences(data) -> List[List[List[int]]]:
    def is_grid(value):
        return (isinstance(value, list) and len(value) == 8
                and all(isinstance(row, list) and len(row) == 8
                        and all(isinstance(pid, int) and 0 <= pid <= 32 for pid in row)
                        for row in value))

    if isinstance(data, dict):
        data = data.get("piece_ids")
    if is_grid(data):
        return [data]
    if isinstance(data, list):
        grids = [item.get("piece_ids") if isinstance(item, dict) else item for item in data]
        if all(is_grid(grid) for grid in grids):
            return grids
    return []


def zip_run_directory(run_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in run_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.relative_to(run_dir))
    buffer.seek(0)
    return buffer.read()


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def list_images(directory: Path) -> List[Path]:
    images: List[Path] = []
    if directory.exists():
        for pattern in ("*.png", "*.jpg", "*.jpeg"):
            images.extend(sorted(directory.glob(pattern)))
    return images


def describe_run(run_dir: Path) -> Dict[str, str]:
    meta = load_run_metadata(run_dir)
    report = ""
    if (run_dir / "TAG_CHECK.html").exists():
        report = "TAG_CHECK.html"
    elif (run_dir / "CHECK.html").exists():
        report = "CHECK.html"
    return {
        "run_id": run_dir.name,
        "input_file": meta.get("input_file", ""),
        "mode": meta.get("mode", ""),
        "timestamp": meta.get("timestamp", ""),
        "report": report,
    }


def run_history() -> List[Dict[str, str]]:
    return [describe_run(path) for _, path in discover_runs()]


def load_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def board_to_table(board_ids: List[List[int]]) -> List[Dict[str, int]]:
    rows = []
    for ridx, row in enumerate(board_ids):
        row_label = str(8 - ridx)
        entry = {"rank": row_label}
        for cidx, pid in enumerate(row):
            entry[chr(ord("A") + cidx)] = pid
        rows.append(entry)
    return rows
