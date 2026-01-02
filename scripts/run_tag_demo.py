"""One-command tag-mode runner with visual verification pack.

Usage:
    python scripts/run_tag_demo.py --input <video> [--outdir out/runs/<run_id>]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from otbreview.pipeline.board_detect import detect_and_warp_board_debug
from otbreview.pipeline.decode import decode_moves_from_tags
from otbreview.pipeline.extract import extract_stable_frames_debug
from otbreview.pipeline.pgn import generate_pgn
from otbreview.pipeline.pieces import detect_pieces_tags


def _default_run_dir() -> Path:
    base = Path("out/runs")
    base.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = base / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _copy_input(input_path: Path, run_dir: Path) -> Path:
    dest = run_dir / f"input{input_path.suffix or '.mp4'}"
    if not dest.exists():
        dest.write_bytes(input_path.read_bytes())
    return dest


def _estimate_tag_px(detections: List[Dict]) -> float:
    import numpy as np

    if not detections:
        return 0.0
    perimeters = []
    for det in detections:
        corners = det.get("corners")
        if corners:
            pts = np.array(corners, dtype=float)
            lengths = [np.linalg.norm(pts[i] - pts[(i + 1) % 4]) for i in range(4)]
            perimeters.append(sum(lengths) / 4.0)
    return float(np.mean(perimeters) if perimeters else 0.0)


def _write_metrics(
    board_states: List[Dict],
    corner_counts: List[int],
    debug_dir: Path,
) -> Path:
    metrics_path = debug_dir / "tag_metrics.csv"
    rows = ["frame_index,corners_detected,num_piece_tags,num_unique_ids,confidence_flag"]
    for idx, state in enumerate(board_states):
        detections = state.get("tag_detections", [])
        tags = [d.get("marker_id") for d in detections]
        unique = len(set(tags))
        corners = corner_counts[idx] if idx < len(corner_counts) else 0
        flag = ""
        if corners < 4:
            flag = "NO_CORNERS"
        elif unique < 20:
            flag = "LOW_TAGS"
        elif len(tags) > unique:
            flag = "DUPLICATE_IDS"
        rows.append(f"{idx},{corners},{len(tags)},{unique},{flag}")

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
    grid_overlay: Path | None,
    board_states: List[Dict],
    warnings: List[str],
) -> None:
    def _img_html(label: str, path: Path | None) -> str:
        if path and path.exists():
            rel = path.relative_to(outdir)
            return f"<div class='card'><h4>{label}</h4><img src='{rel}'></div>"
        return ""

    def _board_table_html(board_ids: List[List[int]]) -> str:
        rows = []
        for r, row in enumerate(board_ids):
            cells = "".join(f"<td>{pid or ''}</td>" for pid in row)
            rows.append(f"<tr><th>{8 - r}</th>{cells}</tr>")
        header = "".join(f"<th>{c}</th>" for c in list("ABCDEFGH"))
        return f"<table class='grid'><tr><th></th>{header}</tr>{''.join(rows)}</table>"

    first_state = board_states[0] if board_states else {}
    detections = first_state.get("tag_detections", [])
    board_ids = first_state.get("piece_ids", []) if isinstance(first_state, dict) else []
    board_id_set = {pid for row in board_ids for pid in row if pid}
    unique_ids = len(board_id_set)
    missing_ids = [pid for pid in range(1, 33) if pid not in board_id_set]
    repeated_ids = sorted(
        {conf.get("marker_id") for conf in first_state.get("tag_conflicts", []) if conf.get("reason") == "id" and conf.get("marker_id")}
    )

    overlay_list_html = "".join(
        f'<li><a href="{p.relative_to(outdir)}" target="_blank">{p.name}</a></li>' for p in overlays[:5]
    )
    overlay_imgs_html = "".join(_img_html(f"Tag Overlay {idx+1}", p) for idx, p in enumerate(overlays[:5]))

    auto_diag = []
    if summary["corner"] < 4:
        auto_diag.append("Corners missing — ensure ArUco 0/1/2/3 are fully visible, avoid cropping, keep board flat.")
        auto_diag.append("Recording tips: move camera higher for full board, avoid obstructions on corners, check glare on markers.")
    if unique_ids < 28:
        avg_px = _estimate_tag_px(detections)
        auto_diag.append(
            f"Tags too few — detected {unique_ids}/32 unique IDs. Estimated tag side ~{avg_px:.1f}px; try 5mm tags, move camera closer, improve focus/lighting."
        )
    if repeated_ids:
        auto_diag.append(f"Duplicate IDs detected on the board: {', '.join(map(str, repeated_ids))}. Reprint stickers to avoid duplicates.")
    auto_diag.extend(warnings)

    fail_reasons = []
    if summary["corner"] < 4:
        fail_reasons.append("Corner markers not all detected")
    if unique_ids < 28:
        fail_reasons.append("Unique IDs below 28 on first stable frame")

    html = f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <title>TAG_CHECK</title>
  <style>
    body{{font-family:Arial, sans-serif;background:#0f1116;color:#f1f1f1;padding:20px;}}
    h1{{color: {'#4caf50' if pass_flag else '#ff5252'};}}
    .flex{{display:flex;gap:16px;flex-wrap:wrap;}}
    .card{{background:#1b1e27;padding:12px;border-radius:10px;box-shadow:0 0 10px rgba(0,0,0,.45);}}
    img{{max-width:100%;height:auto;border:1px solid #333;border-radius:8px;}}
    table.grid{{border-collapse:collapse;width:100%;max-width:520px;}}
    th,td{{border:1px solid #333;padding:6px 10px;text-align:center;}}
    ul{{line-height:1.6;}}
  </style>
</head>
<body>
  <h1>Tag Mode Check: {'PASS' if pass_flag else 'FAIL'}</h1>
  <p><strong>Corner markers:</strong> {summary['corner']} | <strong>Unique IDs (first frame):</strong> {summary['start_ids']} | <strong>Coverage:</strong> {summary['coverage']:.2f}</p>
  <div class="flex">
    {_img_html('Stable Frame', stable_first)}
    {_img_html('Warped Board', warped_first)}
    {_img_html('Grid Overlay', grid_overlay)}
    {_img_html('Overlay', outdir / 'debug' / 'tag_overlay_0001.png')}
    {_img_html('Overlay Zoom', outdir / 'debug' / 'tag_overlay_zoom_0001.png')}
    {_img_html('ID Grid', outdir / 'debug' / 'tag_grid_0001.png')}
  </div>
  <div class="card" style="margin-top:20px;">
    <h3>8×8 Board IDs (first stable frame)</h3>
    { _board_table_html(board_ids) if board_ids else '<p>No board_ids.json captured.</p>' }
    <p><strong>Missing IDs:</strong> {', '.join(map(str, missing_ids)) if missing_ids else 'None'}</p>
  </div>
  <div class="card" style="margin-top:20px;">
    <h3>Diagnostics</h3>
    <p>PASS rule: corners_detected == 4 AND unique_ids >= 28 on the first stable frame.</p>
    <ul>{''.join(f'<li>{msg}</li>' for msg in auto_diag) if auto_diag else '<li>All key checks passed.</li>'}</ul>
    {'<p><strong>WHAT FAILED:</strong> ' + '; '.join(fail_reasons) + '</p>' if (not pass_flag and fail_reasons) else ''}
  </div>
  <div class="card" style="margin-top:20px;">
    <h3>Metrics</h3>
    <p><a href="{metrics_path.relative_to(outdir)}" target="_blank">tag_metrics.csv</a> • first 5 overlays below</p>
    <pre>{metrics_path.read_text(encoding='utf-8')}</pre>
    <h4>Frame Overlays</h4>
    <ul>{overlay_list_html if overlay_list_html else '<li>No overlays saved.</li>'}</ul>
    <div class="flex">{overlay_imgs_html}</div>
  </div>
</body>
</html>"""

    (outdir / "TAG_CHECK.html").write_text(html, encoding="utf-8")
def main() -> None:
    parser = argparse.ArgumentParser(description="Run tag-mode detection + report")
    parser.add_argument("--input", required=True, help="Input video path")
    parser.add_argument("--outdir", required=False, help="Output directory (default out/runs/<run_id>)")
    parser.add_argument("--fps", type=float, default=3.0, help="Target FPS for stable frames")
    parser.add_argument("--motion-threshold", type=float, default=0.01, help="Motion threshold for stable frames")
    parser.add_argument("--stable-duration", type=float, default=0.7, help="Seconds of stability before capture")
    parser.add_argument("--tag-sensitivity", type=float, default=1.0, help="Multiplier for tag detector area filter")
    parser.add_argument("--disable-clahe", action="store_true", help="Skip CLAHE preprocessing")
    parser.add_argument("--disable-threshold-path", action="store_true", help="Skip threshold/OTSU candidate path")
    parser.add_argument("--save-debug", action="store_true", default=True, help="Save debug overlays")
    parser.add_argument("--no-save-debug", dest="save_debug", action="store_false")
    args = parser.parse_args()

    run_dir = Path(args.outdir) if args.outdir else _default_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = run_dir / "debug"
    overlays_dir = debug_dir / "tag_overlays"
    debug_dir.mkdir(exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"输入视频不存在: {input_path}")

    saved_input = _copy_input(input_path, run_dir)
    print(f"输入文件已保存到 {saved_input}")

    run_meta = {
        "run_id": run_dir.name,
        "input_file": input_path.name,
        "mode": "Tag mode",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "params": {
            "fps": args.fps,
            "motion_threshold": args.motion_threshold,
            "stable_duration": args.stable_duration,
            "tag_sensitivity": args.tag_sensitivity,
            "clahe": not args.disable_clahe,
            "threshold_path": not args.disable_threshold_path,
        },
    }
    (run_dir / "run_meta.json").write_text(json.dumps(run_meta, indent=2, ensure_ascii=False), encoding="utf-8")

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

    warped_boards: List[Tuple[int, Any]] = []
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
    warnings: List[str] = []
    for idx, warped in warped_boards:
        state = detect_pieces_tags(
            warped,
            idx,
            str(overlays_dir),
            min_area_ratio=0.0005 * args.tag_sensitivity,
            enable_clahe=not args.disable_clahe,
            enable_threshold=not args.disable_threshold_path,
        )
        board_states.append(state)
        overlay_files.append(overlays_dir / f"overlay_{idx + 1:04d}.png")
        warnings.extend(state.get("tag_warnings", []))

    board_json = json.dumps([s['piece_ids'] for s in board_states], indent=2)
    (debug_dir / "board_ids.json").write_text(board_json, encoding="utf-8")
    (run_dir / "board_ids.json").write_text(board_json, encoding="utf-8")

    print("[4/5] 解码PGN…")
    try:
        moves, confidence = decode_moves_from_tags(board_states, output_dir=str(debug_dir))
        pgn = generate_pgn(moves)
        (run_dir / "game.pgn").write_text(pgn, encoding="utf-8")
        from otbreview.pipeline.pgn import generate_moves_json

        moves_json = generate_moves_json(moves)
        (run_dir / "moves.json").write_text(json.dumps(moves_json, indent=2), encoding="utf-8")
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
        grid_overlay=debug_dir / "grid_overlay.png",
        board_states=board_states,
        warnings=warnings,
    )
    print(f"完成: {run_dir/'TAG_CHECK.html'}")


if __name__ == "__main__":
    main()
