#!/usr/bin/env python3
"""One-command tag-mode demo runner.

Pipeline: stable frame extraction -> board warp -> tag detection -> PGN decode -> TAG_CHECK.html
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from otbreview.pipeline.extract import extract_stable_frames
from otbreview.pipeline.board_detect import detect_and_warp_board
from otbreview.pipeline.pieces import detect_pieces_tags
from otbreview.pipeline.decode import decode_moves_from_tags
from otbreview.pipeline.pgn import generate_pgn


def _write_metrics(board_states: List[Dict], corner_counts: List[int], debug_dir: Path) -> Path:
    metrics_path = debug_dir / "tag_metrics.csv"
    expected = 32
    rows = ["frame,corner_markers,tag_ids,occupied_squares,coverage,warnings"]
    for idx, state in enumerate(board_states):
        grid = state.get("piece_ids", [])
        flat = [pid for row in grid for pid in row if pid]
        unique = len(set(flat))
        occupied = len(flat)
        coverage = occupied / expected if expected else 0
        warnings = list(state.get("tag_warnings", []))
        if idx == 0 and unique < 20:
            warnings.append("LOW CONFIDENCE: 起始局面标签不足20")
        rows.append(
            f"{idx},{corner_counts[idx] if idx < len(corner_counts) else 0},{unique},{occupied},{coverage:.2f},\"{'; '.join(warnings)}\""
        )

    metrics_path.write_text("\n".join(rows), encoding="utf-8")
    return metrics_path


def _build_tag_check_html(outdir: Path, metrics_path: Path, overlays: List[Path], pass_flag: bool, summary: Dict) -> None:
    overlay_list_html = "".join(
        f'<li><a href="{p.relative_to(outdir)}" target="_blank">{p.name}</a></li>' for p in overlays
    )
    html = f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <title>TAG_CHECK</title>
  <style>
    body{{font-family:Arial, sans-serif;background:#111;color:#eee;padding:20px;}}
    h1{{color: {'#4caf50' if pass_flag else '#ff9800'};}}
    .grid{{display:flex;gap:20px;flex-wrap:wrap;}}
    .card{{background:#1e1e1e;padding:15px;border-radius:8px;box-shadow:0 0 10px rgba(0,0,0,.4);}}
    img{{max-width:100%;height:auto;border:1px solid #333;border-radius:6px;}}
    table{{border-collapse:collapse;width:100%;}}
    th,td{{border:1px solid #444;padding:6px 10px;text-align:left;}}
  </style>
</head>
<body>
  <h1>Tag Mode Check: {'PASS' if pass_flag else 'NEEDS ATTENTION'}</h1>
  <p><strong>Corner markers:</strong> {summary['corner']} | <strong>Start IDs:</strong> {summary['start_ids']} | <strong>Coverage:</strong> {summary['coverage']:.2f}</p>
  <div class="grid">
    <div class="card"><h3>Overlay</h3><img src="debug/tag_overlay.png" alt="overlay"></div>
    <div class="card"><h3>Zoom x2</h3><img src="debug/tag_overlay_zoom.png" alt="zoom"></div>
    <div class="card"><h3>ID Grid</h3><img src="debug/tag_grid.png" alt="grid"></div>
    <div class="card"><h3>Missing IDs</h3><img src="debug/tag_missing_ids.png" alt="missing"></div>
  </div>
  <div class="card" style="margin-top:20px;">
    <h3>Metrics</h3>
    <p><a href="{metrics_path.relative_to(outdir)}" target="_blank">tag_metrics.csv</a></p>
    <pre>{metrics_path.read_text(encoding='utf-8')}</pre>
  </div>
  <div class="card" style="margin-top:20px;">
    <h3>Frame Overlays</h3>
    <ul>{overlay_list_html}</ul>
  </div>
</body>
</html>"""

    (outdir / "TAG_CHECK.html").write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tag-mode detection + report")
    parser.add_argument("--input", required=True, help="Input video path")
    parser.add_argument("--outdir", default="out/tag_demo", help="Output root directory")
    parser.add_argument("--motion-threshold", type=float, default=0.01, help="Motion threshold for stable frames")
    parser.add_argument("--stable-duration", type=float, default=0.5, help="Seconds of stability before capture")
    args = parser.parse_args()

    run_dir = Path(args.outdir) / datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_dir = run_dir / "debug"
    overlays_dir = debug_dir / "tag_overlays"
    run_dir.mkdir(parents=True, exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)

    print("[1/5] 抽取稳定帧…")
    stable_frames = extract_stable_frames(
        video_path=args.input,
        output_dir=str(debug_dir / "stable_frames"),
        motion_threshold=args.motion_threshold,
        stable_duration=args.stable_duration,
    )
    print(f"  捕获 {len(stable_frames)} 帧")

    warped_boards = []
    corner_counts = []
    print("[2/5] 透视矫正…")
    for frame_path in stable_frames:
        warped, _, corner_count = detect_and_warp_board(frame_path, use_markers=True, output_dir=str(debug_dir / "warped_boards"))
        if warped is None:
            continue
        warped_boards.append(warped)
        corner_counts.append(corner_count)

    board_states: List[Dict] = []
    print("[3/5] 标签识别…")
    for idx, warped in enumerate(warped_boards):
        state = detect_pieces_tags(warped, idx, str(overlays_dir))
        board_states.append(state)

    if not board_states:
        raise SystemExit("未识别到任何棋盘")

    (debug_dir / "board_ids.json").write_text(json.dumps([s['piece_ids'] for s in board_states], indent=2), encoding="utf-8")

    print("[4/5] 解码PGN…")
    moves, confidence = decode_moves_from_tags(board_states, output_dir=str(debug_dir))
    pgn = generate_pgn(moves)
    (run_dir / "game.pgn").write_text(pgn, encoding="utf-8")
    (debug_dir / "step_confidence.json").write_text(json.dumps(confidence, indent=2), encoding="utf-8")

    metrics_path = _write_metrics(board_states, corner_counts, debug_dir)

    start_ids = len(set(pid for row in board_states[0]['piece_ids'] for pid in row if pid))
    coverage = sum(1 for row in board_states[0]['piece_ids'] for pid in row if pid) / 32
    pass_flag = (corner_counts[0] if corner_counts else 0) >= 4 and start_ids >= 28 and coverage > 0.7

    print("[5/5] 生成报告…")
    overlay_files = sorted(overlays_dir.glob("overlay_*.png"))
    _build_tag_check_html(
        outdir=run_dir,
        metrics_path=metrics_path,
        overlays=overlay_files,
        pass_flag=pass_flag,
        summary={"corner": corner_counts[0] if corner_counts else 0, "start_ids": start_ids, "coverage": coverage},
    )
    print(f"完成: {run_dir/'TAG_CHECK.html'}")


if __name__ == "__main__":
    main()
