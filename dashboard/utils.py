from __future__ import annotations

import io
import json
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

import pandas as pd

BASE_OUTDIR = Path("out/runs")


def ensure_outdir() -> Path:
    BASE_OUTDIR.mkdir(parents=True, exist_ok=True)
    return BASE_OUTDIR


def create_run_dir() -> Tuple[Path, str]:
    ensure_outdir()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = BASE_OUTDIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir, run_id


def save_uploaded_file(uploaded_file, run_dir: Path) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".mp4"
    dest = run_dir / f"input_video{suffix}"
    with dest.open("wb") as f:
        f.write(uploaded_file.getbuffer())
    return dest


def stream_process(command: List[str], cwd: Optional[Path] = None) -> Generator[str, None, None]:
    process = subprocess.Popen(
        command,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def generator() -> Generator[str, None, None]:
        if process.stdout:
            for line in process.stdout:
                yield line.rstrip("\n")
        process.wait()
        generator.returncode = process.returncode

    generator.returncode = None  # type: ignore[attr-defined]
    return generator()


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
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, list) and len(first) == 8:
            return first
    if isinstance(data, dict) and "piece_ids" in data:
        grid = data.get("piece_ids")
        if isinstance(grid, list) and len(grid) == 8:
            return grid
    return None


def load_board_sequences(board_path: Path) -> List[List[List[int]]]:
    if not board_path.exists():
        return []
    try:
        data = json.loads(board_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "piece_ids" in data:
        return [data["piece_ids"]]
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
