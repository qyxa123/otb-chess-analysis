#!/usr/bin/env python3
"""One-command tag-mode runner with visual verification pack.

Usage:
    python scripts/run_tag_demo.py --input <video> --outdir out/web_runs/<run_id>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

from otbreview.pipeline.extract import extract_stable_frames_debug
from otbreview.pipeline.board_detect import detect_and_warp_board_debug
from otbreview.pipeline.pieces import detect_pieces_tags
from otbreview.pipeline.decode import decode_moves_from_tags
from otbreview.pipeline.pgn import generate_pgn


def _write_metrics(
    board_states: List[Dict],
    corner_counts: List[int],
    debug_dir: Path,
) -> Path:
    metrics_path = debug_dir / "tag_metrics.csv"
    rows = ["frame_index,num_corner_markers,num_piece_tags,num_unique_piece_ids,confidence_flag"]
    for idx, state in enumerate(board_states):
        grid = state.get("piece_ids", [])
        flat = [pid for row in grid for pid in row if pid]
        unique = len(set(flat))
        confidence_flag = ""
        if idx == 0 and unique < 20:
            confidence_flag = "LOW_CONFIDENCE"
        rows.append(
            f"{idx},{corner_counts[idx] if idx < len(corner_counts) else 0},{len(flat)},{unique},{confidence_flag}"
        )

    metrics_path.write_text("\n".join(rows), encoding="utf-8")
    return metrics_path


def _build_tag_check_html(
    outdir: Path,
    metrics_path: Path,
    overlays: List[Path],
    pass_flag: bool,
    summary: Dict,
    stable_first: Path | None,
    warped_first: Path | None,
) -> None:
    def _img_html(label: str, path: Path | None) -> str:
        if path and path.exists():
            rel = path.relative_to(outdir)
            return f"<div class='card'><h4>{label}</h4><img src='{rel}'></div>"
        return ""

    overlay_list_html = "".join(
        f'<li><a href="{p.relative_to(outdir)}" target="_blank">{p.name}</a></li>' for p in overlays
    )
    html = f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <title>TAG_CHECK</title>
  <style>
    body{{font-family:Arial, sans-serif;background:#0f1116;color:#f1f1f1;padding:20px;}}
    h1{{color: {'#4caf50' if pass_flag else '#ff9800'};}}
    .grid{{display:flex;gap:16px;flex-wrap:wrap;}}
    .card{{background:#1b1e27;padding:12px;border-radius:10px;box-shadow:0 0 10px rgba(0,0,0,.45);}}
    img{{max-width:100%;height:auto;border:1px solid #333;border-radius:8px;}}
    table{{border-collapse:collapse;width:100%;}}
    th,td{{border:1px solid #333;padding:6px 10px;text-align:left;}}
  </style>
</head>
<body>
  <h1>Tag Mode Check: {'PASS' if pass_flag else 'NEEDS ATTENTION'}</h1>
  <p><strong>Corner markers:</strong> {summary['corner']} | <strong>Start unique IDs:</strong> {summary['start_ids']} | <strong>Coverage:</strong> {summary['coverage']:.2f}</p>
  <div class="grid">
    {_img_html('Stable Frame', stable_first)}
    {_img_html('Warped Board', warped_first)}
    {_img_html('Overlay', outdir / 'debug' / 'tag_overlay_0001.png')}
    {_img_html('Overlay Zoom', outdir / 'debug' / 'tag_overlay_zoom_0001.png')}
    {_img_html('ID Grid', outdir / 'debug' / 'tag_grid_0001.png')}
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


def _copy_input(input_path: Path, run_dir: Path) -> None:
    dest = run_dir / input_path.name
    if not dest.exists():
        dest.write_bytes(input_path.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tag-mode detection + report")
    parser.add_argument("--input", required=True, help="Input video path")
    parser.add_argument("--outdir", required=True, help="Output directory (e.g. out/web_runs/<run_id>)")
    parser.add_argument("--fps", type=float, default=3.0, help="Target FPS for stable frames")
    parser.add_argument("--motion-threshold", type=float, default=0.01, help="Motion threshold for stable frames")
    parser.add_argument("--stable-duration", type=float, default=0.7, help="Seconds of stability before capture")
    parser.add_argument("--save-debug", action="store_true", default=True, help="Save debug overlays")
    parser.add_argument("--no-save-debug", dest="save_debug", action="store_false")
    args = parser.parse_args()

    run_dir = Path(args.outdir)
    run_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = run_dir / "debug"
    overlays_dir = debug_dir / "tag_overlays"
    debug_dir.mkdir(exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"输入视频不存在: {input_path}")

    _copy_input(input_path, run_dir)

    print("[1/5] 抽取稳定帧…")
    stable_frames = extract_stable_frames_debug(
        video_path=str(input_path),
        output_dir=str(debug_dir / "stable_frames"),
        motion_csv_path=str(debug_dir / "motion.csv"),
        target_fps=args.fps,
        motion_threshold=args.motion_threshold,
        stable_duration=args.stable_duration,
    )
    print(f"  捕获 {len(stable_frames)} 帧")

    warped_boards: List[Tuple[int, any]] = []
    corner_counts: List[int] = []
    print("[2/5] 透视矫正…")
    warped_dir = debug_dir / "warped_boards"
    warped_dir.mkdir(exist_ok=True)
    stable_first = Path(stable_frames[0]) if stable_frames else None
    warped_first_path: Path | None = None

    for frame_path in stable_frames:
        idx = len(corner_counts)
        success, warped, preview, grid = detect_and_warp_board_debug(
            frame_path=frame_path,
            use_markers=True,
            output_dir=str(warped_dir),
            frame_idx=idx,
        )
        if preview is not None and idx == 0:
            import cv2

            cv2.imwrite(str(debug_dir / "aruco_preview.png"), preview)
        if grid is not None and idx == 0:
            import cv2

            cv2.imwrite(str(debug_dir / "grid_overlay.png"), grid)

        corner_counts.append(4 if success else 0)
        if success and warped is not None:
            warped_boards.append((idx, warped))
            if warped_first_path is None:
                warped_first_path = warped_dir / f"warp_{idx+1:04d}.png"

    if not warped_boards:
        raise SystemExit("未识别到足够的四角标记，无法进入标签检测")

    print("[3/5] 标签识别…")
    board_states: List[Dict] = []
    overlay_files: List[Path] = []
    for idx, warped in warped_boards:
        state = detect_pieces_tags(warped, idx, str(overlays_dir))
        board_states.append(state)
        overlay_files.append(overlays_dir / f"overlay_{idx + 1:04d}.png")

    board_json = json.dumps([s['piece_ids'] for s in board_states], indent=2)
    (debug_dir / "board_ids.json").write_text(board_json, encoding="utf-8")
    (run_dir / "board_ids.json").write_text(board_json, encoding="utf-8")

    print("[4/5] 解码PGN…")
    try:
        moves, confidence = decode_moves_from_tags(board_states, output_dir=str(debug_dir))
        pgn = generate_pgn(moves)
        (run_dir / "game.pgn").write_text(pgn, encoding="utf-8")
        (debug_dir / "step_confidence.json").write_text(json.dumps(confidence, indent=2), encoding="utf-8")
    except Exception as exc:  # pragma: no cover - 解码失败不阻断整体流程
        print(f"  PGN解码失败: {exc}")

    metrics_path = _write_metrics(board_states, corner_counts, debug_dir)

    start_ids = len(set(pid for row in board_states[0]['piece_ids'] for pid in row if pid)) if board_states else 0
    coverage = sum(1 for row in board_states[0]['piece_ids'] for pid in row if pid) / 32 if board_states else 0
    pass_flag = (corner_counts[0] if corner_counts else 0) >= 4 and start_ids >= 28

    print("[5/5] 生成报告…")
    overlay_files = sorted([p for p in overlay_files if p.exists()])
    _build_tag_check_html(
        outdir=run_dir,
        metrics_path=metrics_path,
        overlays=overlay_files,
        pass_flag=pass_flag,
        summary={"corner": corner_counts[0] if corner_counts else 0, "start_ids": start_ids, "coverage": coverage},
        stable_first=stable_first,
        warped_first=warped_first_path,
    )
    print(f"完成: {run_dir/'TAG_CHECK.html'}")


if __name__ == "__main__":
    main()
