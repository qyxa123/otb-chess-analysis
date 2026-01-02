#!/usr/bin/env python3
"""
主流程编排模块
"""

from pathlib import Path
from typing import Optional
import json

from .extract import extract_stable_frames
from .board_detect import detect_and_warp_board
from .tag_detector import detect_piece_tags
from .tag_decode import infer_moves_from_id_grids, load_piece_id_map
from .pgn import generate_pgn
from .analyze import analyze_game
from .classify import classify_moves
from .keymoves import find_key_moves
from otbreview.web.generate import generate_web_replay
import shutil
import cv2


def analyze_video(
    video_path: str,
    outdir: str,
    use_markers: bool = False,
    depth: int = 14,
    pv_length: int = 6
) -> None:
    """
    分析视频文件，生成PGN和分析结果
    
    Args:
        video_path: 输入视频文件路径
        outdir: 输出目录
        use_markers: 是否使用ArUco/AprilTag标记
        depth: Stockfish分析深度
        pv_length: 主变PV长度
    """
    outdir_path = Path(outdir)
    outdir_path.mkdir(parents=True, exist_ok=True)
    debug_dir = outdir_path / "debug"
    debug_dir.mkdir(exist_ok=True)
    
    print("\n=== 步骤1: 抽取稳定帧 ===")
    stable_frames = extract_stable_frames(
        video_path=video_path,
        output_dir=str(debug_dir / "stable_frames"),
        motion_threshold=0.01,  # 可调参数
        stable_duration=0.5  # 可调参数：稳定持续0.5秒
    )
    print(f"抽取到 {len(stable_frames)} 个稳定局面")
    
    if len(stable_frames) < 2:
        raise ValueError("视频中稳定局面太少，无法解析对局")
    
    print("\n=== 步骤2: 棋盘定位与透视矫正 ===")
    warped_boards = []
    grid_overlay_path = debug_dir / "grid_overlay.png"
    
    for i, frame_path in enumerate(stable_frames):
        warped, grid_img = detect_and_warp_board(
            frame_path=frame_path,
            use_markers=use_markers,
            output_dir=str(debug_dir / "warped_boards")
        )
        if warped is None:
            raise ValueError(f"无法检测棋盘 (帧 {i+1})")
        warped_boards.append((frame_path, warped))
        
        # 保存第一帧的网格覆盖图和矫正后的棋盘（用于验证）
        if i == 0:
            if grid_img is not None:
                cv2.imwrite(str(grid_overlay_path), grid_img)
                print(f"  网格覆盖图已保存: {grid_overlay_path}")
            # 保存矫正后的棋盘用于验证
            warped_debug_path = debug_dir / "warped_board_debug.png"
            cv2.imwrite(str(warped_debug_path), warped)
            print(f"  矫正后棋盘已保存: {warped_debug_path} (用于验证)")
    
    print(f"成功定位 {len(warped_boards)} 个棋盘")
    
    print("\n=== 步骤3: 标签棋子识别 ===")
    tag_overlay_dir = debug_dir / "tag_overlays"
    board_grids = []

    for i, (frame_path, warped) in enumerate(warped_boards):
        result = detect_piece_tags(
            warped_board=warped,
            frame_idx=i,
            output_dir=tag_overlay_dir
        )
        grid_info = {
            'index': i,
            'frame': Path(frame_path).name,
            'board_ids': result.board_ids,
            'overlay': str(result.overlay_path.relative_to(outdir_path)) if result.overlay_path else None,
            'tags': [
                {
                    'id': det.marker_id,
                    'row': det.row,
                    'col': det.col,
                    'center': det.center,
                    'area': det.area,
                }
                for det in result.detections
            ]
        }
        board_grids.append(grid_info)

        if i == 0 and result.overlay_path:
            shutil.copy(result.overlay_path, debug_dir / "tag_overlay.png")

    print(f"识别了 {len(board_grids)} 个局面状态")

    print("\n=== 步骤4: 基于ID的走法推断 ===")
    repo_root = Path(__file__).resolve().parents[2]
    piece_map_path = repo_root / "config" / "piece_id_map.json"
    piece_map = load_piece_id_map(piece_map_path)

    board_ids_path = debug_dir / "board_ids.json"
    with open(board_ids_path, 'w', encoding='utf-8') as f:
        json.dump({'piece_map': piece_map, 'frames': board_grids}, f, indent=2, ensure_ascii=False)
    print(f"board_ids.json 已保存: {board_ids_path}")

    moves, move_debug = infer_moves_from_id_grids(
        board_grids=board_grids,
        piece_map=piece_map,
        output_dir=debug_dir
    )

    move_debug_path = debug_dir / "move_trace.json"
    move_debug_path.write_text(json.dumps(move_debug, indent=2, ensure_ascii=False), encoding='utf-8')

    print(f"解码出 {len(moves)} 步走法")
    uncertain_moves = [i for i, m in enumerate(moves) if m == "??"]
    if uncertain_moves:
        print(f"警告: {len(uncertain_moves)} 步无法唯一确定，建议在网页中检查")
    
    print("\n=== 步骤5: 生成PGN ===")
    pgn_content = generate_pgn(moves=moves)
    pgn_path = outdir_path / "game.pgn"
    with open(pgn_path, 'w', encoding='utf-8') as f:
        f.write(pgn_content)
    print(f"PGN已保存: {pgn_path}")
    
    print("\n=== 步骤6: Stockfish分析 ===")
    analysis = analyze_game(
        pgn_path=str(pgn_path),
        depth=depth,
        pv_length=pv_length
    )
    
    print("\n=== 步骤7: 走法分类 ===")
    classified = classify_moves(analysis=analysis)
    
    print("\n=== 步骤8: 关键走法识别 ===")
    key_moves = find_key_moves(analysis=classified)
    
    # 合并分析结果
    full_analysis = {
        'moves': classified,
        'keyMoves': key_moves,
        'metadata': {
            'depth': depth,
            'pv_length': pv_length,
            'uncertain_moves': uncertain_moves
        }
    }
    
    analysis_path = outdir_path / "analysis.json"
    with open(analysis_path, 'w', encoding='utf-8') as f:
        json.dump(full_analysis, f, indent=2, ensure_ascii=False)
    print(f"分析结果已保存: {analysis_path}")
    
    print("\n=== 步骤9: 生成网页复盘 ===")
    html_path = generate_web_replay(
        pgn_path=str(pgn_path),
        analysis_path=str(analysis_path),
        output_path=str(outdir_path / "index.html"),
        confidence=None,
        tag_board_path=str(board_ids_path)
    )
    print(f"网页复盘已生成: {html_path}")
    
    print("\n=== 分析完成 ===")
    print(f"所有结果保存在: {outdir_path}")

