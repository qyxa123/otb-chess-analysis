# OTBReview：实体棋盘视频转棋谱与复盘

本地 Python 工具：视频 → 稳定帧 → 棋盘校正 → 棋子标签识别 → 合法走法 → PGN → Stockfish 分析 → 离线网页复盘。

## 当前支持范围

推荐 **Tag mode**：棋盘四角使用 ArUco 4×4 / 50 的 0、1、2、3，棋子使用 ArUco 5×5 / 100 的 1–32。仓库内的 `aruco_*.png` 和 `assets/piece_tags/` 可供打印。

- 从标准开局开始录制，白棋在画面下方，a8 在左上角。四个角标中心分别对应棋盘左上、右上、右下、左下顶点。
- 固定机位，保持棋盘和标签清晰；每步落子后停留至少一秒，保证能采到稳定局面。标签需要完整边框和白色留边。
- 默认 ID 对应关系见 `config/piece_id_map.json`。主分析流程依据初始位置建立棋子身份。
- **Marker mode 是实验性的无棋子标签占用识别**，依赖棋子颜色、光照和校准，不保证适用于任意棋盘录像。
- 遇到缺帧、遮挡或无法唯一判断的走法，停止解码并保留可靠前缀，明确标记不完整；不会跳过未知走法后继续编造棋谱。
- 标签位置本身无法区别升变后的棋子种类，升变需要人工核对。

这不是已经训练好的任意无标记棋盘识别模型。目前的自动化测试使用合成标签视频，不能代表真实录像的识别准确率。

## 安装与启动

建议 Python 3.10+。macOS / Linux：

```bash
git clone https://github.com/qyxa123/otb-chess-analysis.git
cd otb-chess-analysis
./scripts/start_studio.sh
```

脚本会创建 `.venv`、安装依赖，并启动 Streamlit。打开终端显示的本地网址，在侧边栏选择 **Home / New Analysis**，上传视频、选择 Tag mode，点击 **Analyze**。完成后点击 **Open Review page**。

也可手动启动（Windows 可用 `.venv\Scripts\python` 替换下面的 Python 路径）：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run dashboard/app.py
```

`dashboard_local/app.py` 和根目录 `app.py` 是保留的其他 Streamlit 入口。推荐从 Studio 开始。

### Stockfish

安装本地引擎可获得战术评估、主变和走法分类：

```bash
# macOS
brew install stockfish
# Debian / Ubuntu
sudo apt install stockfish
```

程序自动查找 PATH、Homebrew 路径和 `/usr/games/stockfish`，也可通过环境变量 `STOCKFISH_PATH` 指定可执行文件。

未安装引擎时仍可导出 PGN 和复盘，界面会明确提示只显示基础子力评估，不提供引擎走法评级或准确率。网页复盘内嵌 SVG 棋盘，无需 CDN 或联网加载棋子。

## 命令行

```bash
.venv/bin/python -m otbreview analyze \
  --input your_game.mp4 \
  --outdir out/runs/my_game \
  --use_markers 1 \
  --use-piece-tags 1 \
  --fps 3 \
  --motion-threshold 0.01 \
  --stable-duration 0.5
```

使用 `--use-piece-tags 0` 尝试占用识别；`--use_markers 0` 尝试实验性轮廓定位。指定使用角标时，如果未检测到全部四个角标，会明确失败。

更多参数：

```bash
.venv/bin/python -m otbreview analyze --help
```

## 输出与纠错

每次 Studio 运行独立保存到 `out/runs/<run_id>/`：

```text
input_video.<ext>
run_meta.json / logs.txt
game.pgn / moves.json / analysis.json / index.html
board_ids.json                         # Tag mode
debug/stable_frames/ / warped_boards/ / tag_overlays/
debug/tag_metrics.csv / step_confidence.json
```

Review 页支持棋盘逐步回放、评估曲线和下载。Debug Lab 用于核对角标、8×8 ID 网格和稳定帧；Corrections 可编辑 ID 网格或替换某步 SAN，再生成棋谱与分析。若替换导致后续走法不合法，会截断后续并提示。

诊断用的旧脚本 `scripts/run_debug_pipeline.py`、`scripts/run_tag_demo.py` 保留用于单独生成 CHECK / TAG_CHECK 报告；它们与 Studio 的完整分析入口不同。

## 验证

```bash
.venv/bin/python -m unittest discover -s tests -v
```

测试涵盖稳定帧时间与去重、标签识别、吃子/王车易位/吃过路兵、未知局面停止、PGN 导出、引擎分数视角、缺少引擎的降级、仪表盘错误状态和离线复盘。端到端测试实际编码一段包含 8 个半回合和两次吃子的合成视频，并检查最终 PGN、ID 网格、分析与 SVG 回放一致。
