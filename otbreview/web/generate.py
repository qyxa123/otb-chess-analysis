#!/usr/bin/env python3
"""
网页复盘生成模块
功能：生成完整的网页复盘界面（包含棋盘、eval graph、分类、key moves等）
"""

import json
import chess.pgn
from pathlib import Path
from typing import Dict, List, Optional


def generate_web_replay(
    pgn_path: str,
    analysis_path: str,
    output_path: str,
    confidence: Optional[List[Dict]] = None,
    tag_board_path: Optional[str] = None
) -> str:
    """
    生成网页复盘HTML文件
    
    Args:
        pgn_path: PGN文件路径
        analysis_path: analysis.json文件路径
        output_path: 输出HTML文件路径
        confidence: 置信度信息（用于纠错功能）
    
    Returns:
        生成的HTML文件路径
    """
    # 读取PGN
    with open(pgn_path, 'r', encoding='utf-8') as f:
        game = chess.pgn.read_game(f)
    
    if game is None:
        raise ValueError("无法解析PGN文件")
    
    # 读取分析结果
    with open(analysis_path, 'r', encoding='utf-8') as f:
        analysis_data = json.load(f)
    
    moves_list = analysis_data.get('moves', [])
    key_moves = analysis_data.get('keyMoves', [])
    
    tag_data = None
    if tag_board_path:
        tag_path = Path(tag_board_path)
        if tag_path.exists():
            try:
                tag_data = json.loads(tag_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                tag_data = None

    # 生成HTML
    html_content = _generate_html(game, moves_list, key_moves, confidence or [], tag_data)
    
    # 保存文件
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return str(output_file)


def _generate_html(
    game: chess.pgn.Game,
    moves_list: List[Dict],
    key_moves: List[int],
    confidence: List[Dict],
    tag_data: Optional[Dict]
) -> str:
    """
    生成HTML内容
    """
    # 提取走法序列
    board = game.board()
    moves_san = []
    for move in game.mainline_moves():
        moves_san.append(board.san(move))
        board.push(move)
    
    # 准备数据
    moves_data = []
    for i, move_san in enumerate(moves_san):
        move_num = (i // 2) + 1
        is_white = (i % 2) == 0
        
        move_info = {
            'number': move_num,
            'san': move_san,
            'is_white': is_white
        }
        
        # 添加分析信息
        if i < len(moves_list):
            move_info.update(moves_list[i])
        
        # 添加置信度信息
        if i < len(confidence):
            move_info['confidence'] = confidence[i]
        
        moves_data.append(move_info)
    
    # 生成eval数据用于图表
    eval_data = []
    for move_data in moves_list:
        eval_cp = move_data.get('eval_cp', 0)
        eval_mate = move_data.get('eval_mate')
        if eval_mate is not None:
            eval_data.append({'cp': None, 'mate': eval_mate})
        else:
            eval_data.append({'cp': eval_cp, 'mate': None})

    tag_json = json.dumps(tag_data or {}, ensure_ascii=False)

    # 嵌入HTML模板
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OTBReview - 棋局复盘</title>
    <script src="https://cdn.jsdelivr.net/npm/chess.js@1.0.0-beta.4/chess.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chessboardjsx@2.0.0/dist/chessboardjsx.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: #1a1a1a;
            color: #e0e0e0;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: 600px 1fr;
            gap: 20px;
        }}
        
        .board-panel {{
            background: #2a2a2a;
            border-radius: 8px;
            padding: 20px;
        }}
        
        .board-wrapper {{
            width: 560px;
            height: 560px;
            margin: 0 auto;
        }}
        
        .controls {{
            display: flex;
            gap: 10px;
            margin: 20px 0;
            justify-content: center;
        }}
        
        button {{
            padding: 10px 20px;
            background: #4a9eff;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }}
        
        button:hover {{
            background: #3a8eef;
        }}
        
        button:disabled {{
            background: #555;
            cursor: not-allowed;
        }}
        
        .info-panel {{
            background: #2a2a2a;
            border-radius: 8px;
            padding: 20px;
        }}
        
        .move-list {{
            max-height: 400px;
            overflow-y: auto;
            margin-bottom: 20px;
        }}
        
        .move-item {{
            padding: 8px;
            margin: 2px 0;
            background: #333;
            border-radius: 4px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
        }}
        
        .move-item:hover {{
            background: #444;
        }}
        
        .move-item.active {{
            background: #4a9eff;
        }}
        
        .move-item.uncertain {{
            border-left: 3px solid #ff6b6b;
        }}
        
        .eval-bar {{
            width: 100%;
            height: 30px;
            background: #333;
            border-radius: 4px;
            margin: 10px 0;
            position: relative;
            overflow: hidden;
        }}
        
        .eval-fill {{
            height: 100%;
            background: linear-gradient(to right, #4a9eff, #8bc34a);
            transition: width 0.3s;
        }}
        
        .eval-graph {{
            width: 100%;
            height: 200px;
            background: #1a1a1a;
            border: 1px solid #444;
            border-radius: 4px;
            margin: 10px 0;
        }}
        
        .classification {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }}
        
        .classification.best {{ background: #4caf50; }}
        .classification.good {{ background: #8bc34a; }}
        .classification.inaccuracy {{ background: #ffc107; }}
        .classification.mistake {{ background: #ff9800; }}
        .classification.blunder {{ background: #f44336; }}
        .classification.book {{ background: #9c27b0; }}

        .fix-button {{
            background: #ff6b6b;
            font-size: 12px;
            padding: 4px 8px;
        }}

        .tag-viewer {{
            margin-top: 30px;
            background: #2a2a2a;
            border-radius: 8px;
            padding: 16px;
        }}

        .tag-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }}

        .tag-layout {{
            display: grid;
            grid-template-columns: 1.2fr 1fr;
            gap: 16px;
            align-items: start;
        }}

        .tag-overlay img {{
            width: 100%;
            border-radius: 6px;
            border: 1px solid #444;
            background: #111;
        }}

        table.tag-grid {{
            border-collapse: collapse;
            width: 100%;
            margin-top: 8px;
        }}

        table.tag-grid td {{
            border: 1px solid #555;
            text-align: center;
            padding: 4px;
            width: 30px;
            height: 30px;
            font-weight: bold;
        }}

        .tag-map {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 8px;
        }}

        .tag-chip {{
            background: #444;
            border-radius: 4px;
            padding: 4px 6px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <h1 style="text-align: center; margin-bottom: 20px;">OTBReview - 棋局复盘</h1>
    
    <div class="container">
        <div class="board-panel">
            <div class="board-wrapper" id="board"></div>
            <div class="controls">
                <button onclick="goToStart()">⏮ 开始</button>
                <button onclick="goToPrevious()">⏪ 上一步</button>
                <button onclick="goToNext()">⏩ 下一步</button>
                <button onclick="goToEnd()">⏭ 结束</button>
                <button onclick="goToNextKey()">▶ 下一个关键点</button>
            </div>
            <div id="eval-bar" class="eval-bar">
                <div class="eval-fill" id="eval-fill" style="width: 50%;"></div>
            </div>
            <div id="current-eval" style="text-align: center; margin: 10px 0;"></div>
        </div>
        
        <div class="info-panel">
            <h3>走法列表</h3>
            <div class="move-list" id="move-list"></div>
            
            <h3>评估曲线</h3>
            <canvas class="eval-graph" id="eval-graph"></canvas>
            
            <h3>当前走法分析</h3>
            <div id="current-analysis"></div>
        </div>
    </div>

    <div class="tag-viewer" id="tag-viewer">
        <div class="tag-header">
            <h2>Tag Overlay Viewer</h2>
            <select id="tag-frame-select"></select>
        </div>
        <div class="tag-layout">
            <div class="tag-overlay">
                <img id="tag-overlay-img" alt="tag overlay" />
            </div>
            <div>
                <h4>8x8 piece_id 表格</h4>
                <table class="tag-grid" id="tag-grid"></table>
                <h4 style="margin-top: 12px;">ID 映射</h4>
                <div class="tag-map" id="tag-map"></div>
            </div>
        </div>
    </div>

    <script>
        const movesData = {json.dumps(moves_data, ensure_ascii=False)};
        const keyMoves = {key_moves};
        const evalData = {json.dumps(eval_data, ensure_ascii=False)};
        const tagData = {tag_json};

        let currentMoveIndex = 0;
        let game = new Chess();
        
        // 初始化棋盘
        function initBoard() {{
            // 使用chessboard.js渲染棋盘
            // 这里简化，实际需要使用chessboard.js库
            updateBoard();
        }}
        
        function updateBoard() {{
            const boardElement = document.getElementById('board');
            // 简化实现：显示FEN
            boardElement.innerHTML = `<div style="text-align: center; padding: 200px; font-size: 18px;">${{game.fen()}}</div>`;
        }}
        
        function updateMoveList() {{
            const listElement = document.getElementById('move-list');
            listElement.innerHTML = '';
            
            movesData.forEach((move, index) => {{
                const item = document.createElement('div');
                item.className = 'move-item' + (index === currentMoveIndex ? ' active' : '');
                if (move.confidence && move.confidence.uncertain) {{
                    item.className += ' uncertain';
                }}
                
                const moveText = move.is_white 
                    ? `${{move.number}}. ${{move.san}}`
                    : `${{move.number}}... ${{move.san}}`;
                
                item.innerHTML = `
                    <span>${{moveText}}</span>
                    <span>
                        ${{move.classification ? `<span class="classification ${{move.classification}}">${{move.classification}}</span>` : ''}}
                        ${{move.confidence && move.confidence.uncertain ? '<button class="fix-button" onclick="fixMove(' + index + ')">Fix</button>' : ''}}
                    </span>
                `;
                item.onclick = () => selectMove(index);
                listElement.appendChild(item);
            }});
        }}
        
        function updateEval() {{
            if (currentMoveIndex < evalData.length) {{
                const eval = evalData[currentMoveIndex];
                const evalElement = document.getElementById('current-eval');
                const fillElement = document.getElementById('eval-fill');
                
                if (eval.mate !== null) {{
                    evalElement.textContent = `Mate in ${{Math.abs(eval.mate)}}`;
                }} else {{
                    const cp = eval.cp || 0;
                    evalElement.textContent = `${{cp > 0 ? '+' : ''}}${{cp.toFixed(1)}}`;
                    // 更新eval bar (0-100映射)
                    const percentage = Math.max(0, Math.min(100, 50 + cp * 2));
                    fillElement.style.width = percentage + '%';
                }}
            }}
        }}
        
        function updateAnalysis() {{
            const analysisElement = document.getElementById('current-analysis');
            if (currentMoveIndex < movesData.length) {{
                const move = movesData[currentMoveIndex];
                let html = '';
                
                if (move.classification) {{
                    html += `<p>分类: <span class="classification ${{move.classification}}">${{move.classification}}</span></p>`;
                }}
                
                if (move.cp_loss !== undefined) {{
                    html += `<p>CP Loss: ${{move.cp_loss.toFixed(1)}}</p>`;
                }}
                
                if (move.pv && move.pv.length > 0) {{
                    html += `<p>主变: ${{move.pv.join(' ')}}</p>`;
                    html += `<button onclick="showFollowUp(${{currentMoveIndex}})">Show Follow-up</button>`;
                }}
                
                analysisElement.innerHTML = html;
            }}
        }}
        
        function selectMove(index) {{
            currentMoveIndex = index;
            game.reset();
            
            for (let i = 0; i <= index && i < movesData.length; i++) {{
                if (i > 0) {{
                    try {{
                        game.move(movesData[i].san);
                    }} catch (e) {{
                        console.error('Invalid move:', movesData[i].san);
                    }}
                }}
            }}
            
            updateBoard();
            updateMoveList();
            updateEval();
            updateAnalysis();
        }}
        
        function goToStart() {{
            selectMove(0);
        }}
        
        function goToPrevious() {{
            if (currentMoveIndex > 0) {{
                selectMove(currentMoveIndex - 1);
            }}
        }}
        
        function goToNext() {{
            if (currentMoveIndex < movesData.length - 1) {{
                selectMove(currentMoveIndex + 1);
            }}
        }}
        
        function goToEnd() {{
            selectMove(movesData.length - 1);
        }}
        
        function goToNextKey() {{
            const nextKey = keyMoves.find(k => k > currentMoveIndex);
            if (nextKey !== undefined) {{
                selectMove(nextKey);
            }} else {{
                goToEnd();
            }}
        }}
        
        function fixMove(index) {{
            // TODO: 实现纠错功能
            alert('纠错功能待实现');
        }}
        
        function showFollowUp(index) {{
            // TODO: 实现PV播放
            alert('Follow-up功能待实现');
        }}

        function initTagViewer() {{
            const viewer = document.getElementById('tag-viewer');
            if (!tagData || !tagData.frames || tagData.frames.length === 0) {{
                viewer.style.display = 'none';
                return;
            }}

            const select = document.getElementById('tag-frame-select');
            select.innerHTML = '';
            tagData.frames.forEach((frame, idx) => {{
                const option = document.createElement('option');
                option.value = idx;
                option.textContent = `帧 ${{idx}} (${{frame.frame || ''}})`;
                select.appendChild(option);
            }});

            select.onchange = renderTagFrame;
            renderTagFrame();
            renderTagMap();
        }}

        function renderTagFrame() {{
            if (!tagData || !tagData.frames || tagData.frames.length === 0) return;
            const select = document.getElementById('tag-frame-select');
            const idx = parseInt(select.value || '0', 10);
            const frame = tagData.frames[Math.max(0, Math.min(idx, tagData.frames.length - 1))];
            const img = document.getElementById('tag-overlay-img');
            if (frame.overlay) {{
                img.src = frame.overlay;
            }}
            img.alt = frame.frame || '';

            const grid = document.getElementById('tag-grid');
            grid.innerHTML = '';
            (frame.board_ids || []).forEach((row) => {{
                const tr = document.createElement('tr');
                row.forEach((cell) => {{
                    const td = document.createElement('td');
                    td.textContent = cell === 0 ? '' : cell;
                    tr.appendChild(td);
                }});
                grid.appendChild(tr);
            }});
        }}

        function renderTagMap() {{
            const mapEl = document.getElementById('tag-map');
            mapEl.innerHTML = '';
            if (!tagData || !tagData.piece_map) return;

            Object.entries(tagData.piece_map).forEach(([pid, info]) => {{
                const chip = document.createElement('div');
                chip.className = 'tag-chip';
                const name = info.name ? ` (${{info.name}})` : '';
                chip.textContent = `ID ${{pid}}: ${{info.symbol}} @ ${{info.square}}${{name}}`;
                mapEl.appendChild(chip);
            }});
        }}

        // 初始化
        initBoard();
        updateMoveList();
        updateEval();
        updateAnalysis();
        initTagViewer();
    </script>
</body>
</html>
"""
    return html

