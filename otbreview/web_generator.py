import json
import os
from typing import Dict, List

from .utils import ensure_dir


TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>OTBReview</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; background: #f7f7f7; }
    .layout { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 16px; }
    .card { background: white; border-radius: 8px; padding: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); }
    #evalChart { width: 100%; height: 200px; }
    .low-confidence { color: #c0392b; font-weight: bold; }
    .move-list { max-height: 500px; overflow: auto; }
    .move-item { cursor: pointer; padding: 4px 0; border-bottom: 1px solid #eee; }
    .controls button { margin-right: 6px; }
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/chess.js/1.0.0/chess.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/chessboardjs/1.0.0/chessboard-1.0.0.min.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/chessboardjs/1.0.0/chessboard-1.0.0.min.css" />
</head>
<body>
  <h2 style="padding:12px">OTBReview - Local Game Review</h2>
  <div class="layout">
    <div class="card">
      <div id="board" style="width:420px"></div>
      <div class="controls">
        <button onclick="jump(0)">|&lt;</button>
        <button onclick="step(-1)">&lt;</button>
        <button onclick="step(1)">&gt;</button>
        <button onclick="jump(moves.length)">&gt;|</button>
      </div>
      <div id="coach"></div>
    </div>
    <div class="card">
      <h3>Moves</h3>
      <div id="accuracy"></div>
      <div id="evalChart"></div>
      <div class="move-list" id="moveList"></div>
    </div>
  </div>
  <script>
    const data = {{DATA}};
    const moves = data.moves;
    const board = Chessboard('board', 'start');
    const game = new Chess();
    let idx = 0;

    function renderList() {
      const container = document.getElementById('moveList');
      container.innerHTML = '';
      moves.forEach((m, i) => {
        const div = document.createElement('div');
        div.className = 'move-item';
        if (m.confidence < 0.6) div.classList.add('low-confidence');
        div.innerText = `${i+1}. ${m.san} (${m.classification || ''})`;
        div.onclick = () => { idx = i + 1; replay(); };
        if (m.candidates) {
          const sel = document.createElement('select');
          sel.onchange = () => { applyCorrection(i, sel.value); };
          m.candidates.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.san;
            opt.innerText = `${c.san} (${(c.confidence*100).toFixed(0)}%)`;
            sel.appendChild(opt);
          });
          div.appendChild(sel);
        }
        container.appendChild(div);
      });
      computeAccuracy();
    }

    function computeAccuracy() {
      const penalties = moves.map(m => Math.min(Math.abs(m.delta_cp || 0), 800));
      const score = Math.max(0, 100 - (penalties.reduce((a,b)=>a+b,0)/Math.max(1,penalties.length))/8);
      document.getElementById('accuracy').innerText = `Estimated accuracy: ${score.toFixed(1)}`;
    }

    function step(delta) { idx = Math.min(Math.max(0, idx + delta), moves.length); replay(); }
    function jump(to) { idx = to; replay(); }

    function replay() {
      game.reset();
      for (let i=0;i<idx;i++) {
        game.move(moves[i].san, {sloppy:true});
      }
      board.position(game.fen());
      const current = moves[idx-1];
      document.getElementById('coach').innerText = current ? `Move ${idx}: ${current.classification || ''} Δ${current.delta_cp||0}` : '';
    }

    function applyCorrection(moveIndex, san) {
      // simple client-side correction to allow replay without re-running pipeline
      moves[moveIndex].san = san;
      for (let i = moveIndex + 1; i < moves.length; i++) {
        moves[i].classification = 'Pending recompute';
      }
      renderList();
      replay();
    }

    function drawEval() {
      const canvas = document.createElement('canvas');
      canvas.width = 600; canvas.height = 200;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#fafafa'; ctx.fillRect(0,0,canvas.width,canvas.height);
      ctx.strokeStyle = '#2c3e50';
      ctx.beginPath();
      moves.forEach((m, i) => {
        const x = (i / Math.max(1, moves.length-1)) * (canvas.width-20) + 10;
        const y = canvas.height/2 - Math.max(-400, Math.min(400, m.evaluation_cp||0)) / 4;
        if (i === 0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
      });
      ctx.stroke();
      document.getElementById('evalChart').appendChild(canvas);
    }

    renderList();
    replay();
    drawEval();
  </script>
</body>
</html>
"""


def render_webpage(analysis: Dict, outdir: str) -> str:
    ensure_dir(outdir)
    html_path = os.path.join(outdir, "index.html")
    html = TEMPLATE.replace("{{DATA}}", json.dumps(analysis))
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return html_path
