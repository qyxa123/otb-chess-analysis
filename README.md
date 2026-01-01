# OTBReview (MVP1-MVP3)

本仓库提供一个离线的 OTBReview 管线：从手机俯拍棋盘视频抽帧 → 棋盘定位与透视矫正 → 棋子占位/颜色识别 → 合法走法解码生成 PGN → Stockfish 本地分析 → 生成本地网页复盘（含纠错入口与 eval 图表）。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# 可选：安装 stockfish（例如 Ubuntu: sudo apt-get install stockfish）
```

## CLI

```bash
python -m otbreview.cli analyze --input /path/to/game.mp4 --outdir /tmp/output
# 或使用内置 Demo（不需要视频）
python -m otbreview.cli analyze --demo --outdir /tmp/demo
```

参数：
- `--engine`: Stockfish 二进制路径（默认从 PATH 查找）。
- `--depth`: 分析深度（默认 12）。
- `--demo`: 使用合成稳定帧模拟完整流程。

运行后 `outdir` 中会包含：
- `game.pgn`: 通过合法性约束解码的 PGN。
- `analysis.json`: 每步占位/置信度/Stockfish 评估/分类/PV。
- `web/index.html`: 本地打开即可浏览的复盘页面（含纠错入口）。
- `debug/`: 稳定帧、透视矫正、每格切块等调试产物。

## Pipeline 说明

1. **解码与抽帧（`FrameExtractor`）**：基于帧间差分的运动能量，在稳定段保存代表帧到 `debug/stable_frames/`。
2. **棋盘定位（`BoardLocator`）**：优先使用 ArUco 4 角点，失败则回退到最大四边形轮廓；输出 `warped_board.png` 与 `grid_overlay.png`。
3. **棋子占位/颜色（`PieceDetector`）**：按 8x8 分块做 Otsu 前景检测，输出 `empty/white/black` 占位图。
4. **合法性约束解码（`MoveReconstructor`）**：对每帧占位与上一步局面枚举合法走法，按占位差异打分，输出候选与置信度。
5. **Stockfish 分析（`StockfishModule`）**：为每步给出 eval、PV、分类（Best/Excellent/Good/Inaccuracy/Mistake/Blunder），引擎缺失时回退为标记信息。
6. **网页复盘（`web/index.html`）**：使用 chess.js + chessboard.js 渲染走棋、eval 简易折线、低置信度提示与下拉纠错；修改后可即时回放并标记“Pending recompute”。

## MVP 划分与运行
- **MVP-1**：`--demo` 生成合成稳定帧 → 棋盘透视 → PGN → 网页。产物：`debug/warped_board.png`、`game.pgn`、`web/index.html`。
- **MVP-2**：开启真实 `--input` 视频，占位/颜色识别 + 合法性约束恢复走法，`analysis.json` 中含 `confidence` 与候选。
- **MVP-3**：安装 Stockfish 后，`analysis.json` 补充 eval/PV/分类，网页展示 eval 曲线、coach 文案位（当前以分类+Δcp 展示）。

## 调试与参数
- 在 `otbreview/frame_extractor.py` 调整 `motion_threshold`、`stable_seconds` 控制抽帧灵敏度。
- ArUco 棋盘增强：在棋盘四角贴 ID 0/1/2/3 的 4x4 ArUco，`BoardLocator` 自动优先使用。
- 若没有 Stockfish，CLI 会输出“Engine missing”分类，网页仍可回放。

## 样例输出
使用内置 Demo：
```bash
python -m otbreview.cli analyze --demo --outdir /tmp/otb_demo
open /tmp/otb_demo/web/index.html
```

Debug 目录：`debug/stable_frames/*.png`（稳定帧）、`debug/warped_board.png`（透视矫正）、`debug/cells/*.png`（每格裁剪/占位图）。
