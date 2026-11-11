#!/usr/bin/env python3
"""Generate a self-contained chess replay that also works without internet."""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Dict, List, Optional

import chess
import chess.pgn
import chess.svg
from self_analysis import parse_pgn_text


def generate_web_replay(
    pgn_path: str,
    analysis_path: str,
    output_path: str,
    confidence: Optional[List[Dict]] = None,
    tag_board_path: Optional[str] = None,
) -> str:
    """Write an offline replay with a board for every position in the PGN."""
    with open(pgn_path, encoding="utf-8") as source:
        game = parse_pgn_text(source.read())
    with open(analysis_path, encoding="utf-8") as source:
        analysis = json.load(source)

    tag_data = None
    if tag_board_path and Path(tag_board_path).exists():
        tag_path = Path(tag_board_path)
        try:
            tag_data = _load_tags(tag_path)
        except (OSError, ValueError, TypeError):
            tag_data = None

    content = _generate_html(
        game, analysis.get("moves", []), analysis.get("keyMoves", []),
        confidence or [], tag_data,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return str(destination)


def _load_tags(path: Path) -> Dict:
    """Accept both raw ID grids and the structured tag viewer format."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        data = {"frames": [{"board_ids": grid} for grid in data]}
    if not isinstance(data, dict):
        return {"frames": []}
    frames = []
    for index, item in enumerate(data.get("frames", [])):
        frame = dict(item) if isinstance(item, dict) else {"board_ids": item}
        candidates = []
        if frame.get("overlay"):
            candidates.append(path.parent / str(frame["overlay"]))
        candidates.extend([
            path.parent / "tag_overlays" / f"overlay_{index + 1:04d}.png",
            path.parent / "debug" / "tag_overlays" / f"overlay_{index + 1:04d}.png",
        ])
        frame.pop("overlay", None)
        for candidate in candidates:
            if candidate.is_file():
                mime = mimetypes.guess_type(candidate.name)[0] or "image/png"
                if mime in {"image/png", "image/jpeg", "image/webp"}:
                    frame["overlay"] = f"data:{mime};base64," + base64.b64encode(candidate.read_bytes()).decode("ascii")
                    break
        frames.append(frame)
    return {"frames": frames, "piece_map": data.get("piece_map", {})}


def _replay_payload(game, moves_list, key_moves, confidence, tag_data):
    analysis_by_ply = {}
    for index, entry in enumerate(moves_list):
        if isinstance(entry, dict):
            analysis_by_ply[entry.get("move_number", index)] = entry
    board = game.board()
    positions = []

    def add_position(ply, label, move=None):
        entry = analysis_by_ply.get(ply, {})
        positions.append({
            "ply": ply,
            "label": label,
            "san": entry.get("move_san", label),
            "fen": board.fen(),
            "svg": chess.svg.board(board=board, lastmove=move, size=560),
            "eval_cp": entry.get("eval_cp"),
            "eval_mate": entry.get("eval_mate"),
            "classification": entry.get("classification", ""),
            "cp_loss": entry.get("cp_loss"),
            "pv": entry.get("pv", []),
            "analysis_source": entry.get("analysis_source", ""),
            "confidence": confidence[ply - 1] if 0 < ply <= len(confidence) else {},
        })

    add_position(0, "初始局面")
    for ply, move in enumerate(game.mainline_moves(), 1):
        san = board.san(move)
        label = f"{board.fullmove_number}{'.' if board.turn else '...'} {san}"
        board.push(move)
        add_position(ply, label, move)
    return {
        "positions": positions,
        "key_moves": sorted({k for k in key_moves if isinstance(k, int) and 0 < k < len(positions)}),
        "tags": tag_data or {},
        "partial": any(item.get("uncertain") for item in confidence),
        "pgn": game.accept(chess.pgn.StringExporter(headers=True, variations=False, comments=True)),
        "players": f"{game.headers.get('White', '?')} — {game.headers.get('Black', '?')}",
    }


def _generate_html(game, moves_list, key_moves, confidence, tag_data) -> str:
    payload = _replay_payload(game, moves_list, key_moves, confidence, tag_data)
    # JSON is inside an HTML script element: '<' must not terminate that element.
    serialized = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace("&", "\\u0026")
    return _HTML.replace("__REPLAY_DATA__", serialized)


_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OTBReview · 棋局复盘</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#171a1d;color:#e9edf0}*{box-sizing:border-box}body{margin:0;padding:24px}main{max-width:1180px;margin:auto}h1{margin:0;font-size:28px}h2{font-size:18px}p{line-height:1.6}.muted{color:#abb5bd;font-size:14px}.layout{display:grid;grid-template-columns:minmax(280px,1.15fr) minmax(280px,1fr);gap:24px}.panel{background:#22272c;padding:20px;border-radius:16px;margin-top:20px}#board{max-width:560px;margin:auto}#board svg{display:block;width:100%;height:auto}.controls{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin:18px 0}button,a.download{background:#3c725a;color:white;border:0;border-radius:7px;padding:10px 13px;cursor:pointer;font:inherit;text-decoration:none}button:hover,a.download:hover{background:#4b8b6e}button:disabled{opacity:.4;cursor:default}.controls button{font-size:14px}#move-list{max-height:300px;overflow:auto;display:grid;grid-template-columns:1fr 1fr;gap:7px}#move-list button{text-align:left;background:#30383f;padding:9px;font-size:14px}#move-list button.active{background:#3c725a;outline:1px solid #8bc9a6}#move-list button.uncertain{border-left:3px solid #e6a23c}#current-label{text-align:center;font-weight:600}#eval-track{height:9px;background:#111;border-radius:8px;overflow:hidden;margin-top:14px}#eval-fill{height:100%;background:#f3f4ed;width:50%;transition:width .15s}#current-eval{text-align:center;margin-top:8px}#graph{width:100%;height:130px;background:#1b2024;border-radius:8px}#fen{word-break:break-all;font:12px monospace;color:#abb5bd}#source{border-left:3px solid #7bb491;padding-left:10px}#current-analysis p{margin:8px 0}.tag-layout{display:grid;grid-template-columns:1fr 1fr;gap:20px}.tag-layout img{max-width:100%;max-height:400px}select{font:inherit;background:#30383f;border:1px solid #56616a;color:inherit;padding:8px;border-radius:6px}table{border-collapse:collapse;width:100%;margin-top:15px}td{border:1px solid #53606b;text-align:center;height:32px}.hidden{display:none!important}@media(max-width:740px){body{padding:14px}.layout,.tag-layout{grid-template-columns:1fr}.panel{padding:14px}.layout{gap:0}h1{font-size:24px}}
</style>
</head>
<body><main>
<h1>OTBReview · 棋局复盘</h1><p id="players" class="muted"></p>
<p id="source" class="muted"></p>
<div class="layout">
<section class="panel"><div id="board" aria-label="棋盘"></div><p id="current-label" aria-live="polite"></p>
<div class="controls"><button id="start">⏮ 开始</button><button id="previous">← 上一步</button><button id="next">下一步 →</button><button id="end">结束 ⏭</button><button id="next-key">下一关键步</button></div>
<div id="eval-track"><div id="eval-fill"></div></div><div id="current-eval"></div><p class="muted">使用 ← → 切换走法，Home / End 跳至首尾。评估值以白方为正。</p><p id="fen"></p>
</section>
<section class="panel"><h2>走法列表</h2><div id="move-list"></div><h2>评估曲线</h2><svg id="graph" viewBox="0 0 500 130" role="img" aria-label="白方视角评估曲线"></svg><h2>当前局面</h2><div id="current-analysis"></div><p><a class="download" id="download-pgn" download="game.pgn">下载 PGN</a></p></section>
</div>
<section class="panel hidden" id="tag-viewer"><h2>标签识别检查</h2><select id="tag-select" aria-label="选择标签识别帧"></select><div class="tag-layout"><img id="tag-image" alt="标签识别叠加图"><div><table id="tag-grid"></table><p id="tag-map" class="muted"></p></div></div></section>
</main>
<script id="replay-data" type="application/json">__REPLAY_DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('replay-data').textContent);
const positions=data.positions;
let current=0;
const $=id=>document.getElementById(id);
$('players').textContent=data.players;
const material=positions.some(p=>p.analysis_source==='material');
$('source').textContent=material?'基础子力估值：未使用 Stockfish，不能判断战术或走法质量。':'Stockfish 局面评估';
if(!positions.some(p=>p.analysis_source)) $('source').textContent='棋局复盘';
if(data.partial) $('source').textContent+=' · 识别中断，仅显示可靠的棋谱前缀，请核对原视频。';
$('download-pgn').href=URL.createObjectURL(new Blob([data.pgn],{type:'application/x-chess-pgn;charset=utf-8'}));
const buttons=[];
positions.forEach((position,index)=>{
 const button=document.createElement('button');button.type='button';button.textContent=position.label;
 if(position.confidence&&position.confidence.uncertain) button.classList.add('uncertain');
 button.onclick=()=>select(index);$('move-list').appendChild(button);buttons.push(button);
});
function score(position){
 if(position.eval_mate!==null&&position.eval_mate!==undefined){
  return (position.eval_cp!==null&&position.eval_cp!==undefined?position.eval_cp:position.eval_mate)*1>=0?1000:-1000;
 }
 return Number.isFinite(position.eval_cp)?position.eval_cp:null;
}
function drawGraph(){
 const values=positions.map(score);const ns='http://www.w3.org/2000/svg';$('graph').replaceChildren();
 const zero=document.createElementNS(ns,'line');Object.entries({x1:0,x2:500,y1:65,y2:65,stroke:'#53606b'}).forEach(([k,v])=>zero.setAttribute(k,v));$('graph').appendChild(zero);
 let segment=[];
 function drawSegment(){if(!segment.length)return;const line=document.createElementNS(ns,'polyline');line.setAttribute('points',segment.join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','#8bc9a6');line.setAttribute('stroke-width','2');$('graph').appendChild(line);segment=[];}
 values.forEach((value,index)=>{if(value===null){drawSegment();return;}const x=index*500/Math.max(1,values.length-1),y=65-Math.max(-1000,Math.min(1000,value))*0.06;segment.push(`${x},${y}`);});drawSegment();
 const cursor=document.createElementNS(ns,'line');const x=current*500/Math.max(1,values.length-1);Object.entries({x1:x,x2:x,y1:0,y2:130,stroke:'#d9a757','stroke-width':2}).forEach(([k,v])=>cursor.setAttribute(k,v));$('graph').appendChild(cursor);
}
function addText(text){const p=document.createElement('p');p.textContent=text;$('current-analysis').appendChild(p);}
function select(index){
 current=Math.max(0,Math.min(positions.length-1,index));const position=positions[current];
 $('board').innerHTML=position.svg;$('current-label').textContent=position.label;$('fen').textContent=position.fen;
 buttons.forEach((button,i)=>{button.classList.toggle('active',i===current);button.setAttribute('aria-current',i===current?'step':'false');});
 buttons[current].scrollIntoView({block:'nearest',behavior:'smooth'});
 $('start').disabled=current===0;$('previous').disabled=current===0;$('next').disabled=current===positions.length-1;$('end').disabled=current===positions.length-1;
 $('next-key').disabled=!data.key_moves.some(k=>k>current);
 const value=score(position);
 $('eval-fill').style.width=value===null?'50%':`${50+50*Math.tanh(value/500)}%`;
 if(position.eval_mate!==null&&position.eval_mate!==undefined){$('current-eval').textContent=`${value>=0?'白方':'黑方'}将杀 · #${Math.abs(position.eval_mate)}`;}
 else if(value===null){$('current-eval').textContent='暂无评估';}
 else{$('current-eval').textContent=`${value>0?'+':''}${(value/100).toFixed(2)}${position.analysis_source==='material'?'（仅子力）':''}`;}
 $('current-analysis').replaceChildren();
 if(position.classification&&!['initial','material'].includes(position.classification))addText(`走法分类：${position.classification}`);
 if(Number.isFinite(position.cp_loss)&&position.analysis_source!=='material')addText(`估值损失：${position.cp_loss.toFixed(0)} cp`);
 if(position.pv&&position.pv.length)addText(`当前局面主变：${position.pv.join(' ')}`);
 if(position.confidence&&position.confidence.uncertain)addText('视频识别置信度较低，请在纠错页面核对这一步。');
 if(!$('current-analysis').hasChildNodes())addText(position.analysis_source==='material'?'仅比较双方子力；安装 Stockfish 后可获得战术分析。':'选择走法查看该局面分析。');
 drawGraph();
}
$('start').onclick=()=>select(0);$('previous').onclick=()=>select(current-1);$('next').onclick=()=>select(current+1);$('end').onclick=()=>select(positions.length-1);$('next-key').onclick=()=>{const next=data.key_moves.find(k=>k>current);if(next!==undefined)select(next);};
document.addEventListener('keydown',event=>{if(['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName))return;const actions={ArrowLeft:()=>select(current-1),ArrowRight:()=>select(current+1),Home:()=>select(0),End:()=>select(positions.length-1)};if(actions[event.key]){event.preventDefault();actions[event.key]();}});
function renderTag(){const frames=data.tags.frames||[];const frame=frames[Number($('tag-select').value)]||{};$('tag-image').classList.toggle('hidden',!frame.overlay);if(frame.overlay)$('tag-image').src=frame.overlay;$('tag-grid').replaceChildren();(frame.board_ids||[]).forEach(row=>{const tr=document.createElement('tr');row.forEach(id=>{const td=document.createElement('td');td.textContent=id||'';tr.appendChild(td);});$('tag-grid').appendChild(tr);});}
if(data.tags.frames&&data.tags.frames.length){$('tag-viewer').classList.remove('hidden');data.tags.frames.forEach((frame,index)=>{const option=document.createElement('option');option.value=index;option.textContent=`稳定帧 ${index+1}`;$('tag-select').appendChild(option);});$('tag-select').onchange=renderTag;$('tag-map').textContent=Object.entries(data.tags.piece_map||{}).map(([id,info])=>`ID ${id}: ${info.symbol||''} ${info.square||''}`).join(' · ');renderTag();}
select(0);
</script>
</body></html>
'''
