"""Helper utilities for the Streamlit dashboard."""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

import chess
import chess.pgn

from dashboard.utils import BASE_OUTDIR, create_run_dir, stream_process


def ensure_base_outdir() -> Path:
    BASE_OUTDIR.mkdir(parents=True, exist_ok=True)
    return BASE_OUTDIR


def save_uploaded_file(uploaded_file, run_dir: Path) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".mp4"
    dest = run_dir / f"input{suffix}"
    with dest.open("wb") as f:
        f.write(uploaded_file.getbuffer())
    return dest


def load_run_metadata(run_dir: Path) -> Dict:
    meta_path = run_dir / "run_meta.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def write_run_metadata(run_dir: Path, data: Dict) -> None:
    meta_path = run_dir / "run_meta.json"
    try:
        meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def discover_runs() -> List[Tuple[str, Path]]:
    ensure_base_outdir()
    runs = []
    for child in BASE_OUTDIR.iterdir():
        if child.is_dir():
            runs.append((child.name, child))
    runs.sort(reverse=True)
    return runs


def parse_check_status(check_path: Path) -> Optional[str]:
    if not check_path.exists():
        return None
    content = check_path.read_text(encoding="utf-8", errors="ignore")
    # Only inspect rendered status elements; the CSS includes both pass/fail classes.
    status = re.search(r'class=[\"\'][^\"\']*status-banner\s+status-(pass|fail|warning)', content, re.I)
    if status:
        return {"pass": "PASS", "fail": "FAIL", "warning": "WARNING"}[status.group(1).lower()]
    heading = re.search(r'<h[12][^>]*>[^<]*\b(PASS|FAIL)\b[^<]*</h[12]>', content, re.I)
    return heading.group(1).upper() if heading else None


def parse_tag_status(tag_path: Path) -> Optional[str]:
    return parse_check_status(tag_path)


def list_artifacts(run_dir: Path) -> List[Tuple[str, Path]]:
    artifacts = []
    for path in sorted(run_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(run_dir)
            if rel.name == "run_meta.json":
                continue
            artifacts.append((str(rel), path))
    return artifacts


def find_first_image(directory: Path) -> Optional[Path]:
    if not directory.exists():
        return None
    for pattern in ("*.png", "*.jpg", "*.jpeg"):
        matches = sorted(directory.glob(pattern))
        if matches:
            return matches[0]
    return None


def gather_tag_overlays(debug_dir: Path) -> List[Path]:
    overlays_dir = debug_dir / "tag_overlays"
    overlays = sorted(overlays_dir.glob("overlay_*.png")) if overlays_dir.exists() else []
    return overlays


def load_board_ids(run_dir: Path) -> Optional[List[List[int]]]:
    for candidate in [run_dir / "board_ids.json", run_dir / "debug" / "board_ids.json"]:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                return None
    return None


def key_artifacts(run_dir: Path) -> Dict[str, Optional[Path]]:
    debug = run_dir / "debug"
    return {
        "stable": find_first_image(debug / "stable_frames"),
        "warped": find_first_image(debug / "warped_boards"),
        "grid": debug / "grid_overlay.png" if (debug / "grid_overlay.png").exists() else None,
        "aruco": debug / "aruco_preview.png" if (debug / "aruco_preview.png").exists() else None,
        "tag_overlay": debug / "tag_overlay_0001.png" if (debug / "tag_overlay_0001.png").exists() else None,
        "tag_zoom": debug / "tag_overlay_zoom_0001.png" if (debug / "tag_overlay_zoom_0001.png").exists() else None,
        "tag_grid": debug / "tag_grid_0001.png" if (debug / "tag_grid_0001.png").exists() else None,
    }


def run_status(run_dir: Path) -> str:
    status = load_run_metadata(run_dir).get("status")
    if status:
        return {"complete": "PASS", "failed": "FAIL", "running": "RUNNING"}.get(status, status.upper())
    tag_status = parse_tag_status(run_dir / "TAG_CHECK.html")
    check_status = parse_check_status(run_dir / "CHECK.html")
    return tag_status or check_status or "PENDING"


def zip_run_directory(run_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in run_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.relative_to(run_dir))
    buffer.seek(0)
    return buffer.read()


def parse_pgn_advantage(pgn_path: Path) -> Dict[str, object]:
    """Return a material-only graph; material cannot estimate engine accuracy."""
    if not pgn_path.exists():
        return {}
    game = chess.pgn.read_game(io.StringIO(pgn_path.read_text(encoding="utf-8")))
    if game is None or game.errors:
        return {}
    board = game.board()
    values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
    evals, moves = [], []
    for move in game.mainline_moves():
        moves.append(board.san(move))
        board.push(move)
        evals.append(sum(values.get(piece.piece_type, 0) * (1 if piece.color else -1)
                         for piece in board.piece_map().values()))
    return {"evals": evals, "moves": moves} if moves else {}
