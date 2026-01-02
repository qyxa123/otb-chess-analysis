# OTBReview - 实体棋盘视频分析系统

将实体棋盘视频转换为PGN，并使用Stockfish进行复盘分析。

## 功能特性

- 📹 **视频解析**：自动从视频中抽取稳定局面帧
- 🎯 **棋盘定位**：支持ArUco/AprilTag标记或纯视觉检测
- ♟️ **走法识别**：基于合法性约束的解码算法
- 🧠 **Stockfish分析**：本地离线分析，无需会员
- 📊 **可视化复盘**：仿chess.com风格的网页复盘界面
- 🔧 **纠错机制**：低置信度走法可手动修正
- 🏷️ **棋子贴码识别**：支持1-32号棋子贴纸，逐帧还原piece_id网格并解码走法

## Beginner (3 steps)

1. **Install Stockfish + ffmpeg** (macOS):
   ```bash
   brew install stockfish ffmpeg
   ```
2. **Launch the studio app** (creates venv + installs deps):
   ```bash
   ./scripts/start_studio.sh
   ```
3. **Use the browser only**: upload video → choose Marker / Tag → click **Analyze** → hit **Open Review**. Outputs land in `out/runs/<run_id>/` with input_video copy, debug images, game.pgn, analysis.json, index.html, CHECK/TAG_CHECK reports.

## 快速开始

### 全新本地仪表盘（推荐）

一键启动浏览器端 UI，免命令行：

```bash
pip install -r requirements_computer.txt
pip install -r requirements_dashboard.txt
streamlit run dashboard_local/app.py
```

进入首页后可见三个标签页：

- **Upload & Run**：上传 mp4/mov，选择 Marker Mode（仅四角）或 Tag Mode（棋子标签），可调 FPS 采样、稳定阈值、标签灵敏度，点击 Run 即刻执行原有 CLI 流程。
- **Results / Replay**：自动展示稳定帧、warp、grid_overlay.png、aruco_preview.png；Tag 模式额外显示 tag_overlays、8×8 ID 表格、TAG_CHECK/CHECK 内嵌报告，并提供 PGN、board_ids.json、tag_metrics.csv、整包 ZIP 下载。
- **History**：列出 `out/runs/` 内历史 run_id、输入名、PASS/FAIL，点击 Open 可跳转重播。

### OTBReview Studio（Streamlit，多页）

- 入口：`streamlit run dashboard/app.py` 或直接执行 `./scripts/start_studio.sh`。
- 侧边栏页面：
  1) **Home / New Analysis**：上传/拖拽视频，选择模式，展开 Advanced 设置 FPS、motion threshold、tag 预处理开关，点击 **Analyze**。
  2) **Review**：自动查找 `out/runs/<run_id>/index.html` 并内嵌播放，展示优势曲线、命中率、moves 列表、PGN/analysis.json/ZIP 下载。
  3) **Debug Lab**：开发者工具，批量预览 stable/warp/tag overlay、展示 `debug/tag_metrics.csv`、逐帧 board_ids 表格、单帧 rerun 检测与自动诊断（角点缺失、标签过少、重复 ID）。
  4) **Corrections**：人工修正棋盘/走法：编辑 8×8 ID 网格（可加载标准开局映射），保存为 `board_ids_override.json` 并重新解码；在低置信度步数手动替换 SAN 并重新生成 PGN/analysis.json。

### Debug Lab 使用

- 选择 run_id 浏览 `debug/stable_frames/` 与 `debug/tag_overlays/` 缩略图。
- 展示 `tag_metrics.csv` 的角点/标签统计，自动提示低角点/低 ID/重复 ID，并附录诊断建议。
- 选择任意稳定帧，一键重跑角点+warp，并可追加标签检测以快速验证调参。
- 选择帧索引查看 8×8 board_ids 表格，结合 `TAG_CHECK.html` 诊断覆盖率。

### Corrections 工作流

- 在 **Corrections** 选择 run_id → 指定稳定帧 → 逐格修改 ID（0 表示空）。
- 点击保存后会写入 `board_ids_override.json`，并从该帧开始重新解码、生成新的 `game.pgn`、`moves.json`、`analysis.json`。
- 如某步置信度低，可在 Move-level correction 里选择合法 SAN 替换，重新计算后续分析。

### Run 文件夹结构

每次运行都会标准化输出到 `out/runs/<run_id>/`：

```
out/runs/<run_id>/
  input_video.<ext>
  debug/
    stable_frames/
    warped_boards/
    tag_overlays/
    tag_metrics.csv
  board_ids.json
  game.pgn
  analysis.json
  index.html
  CHECK.html or TAG_CHECK.html
  run_meta.json
```

### Tag 模式入门

- 运行命令：`python scripts/run_tag_demo.py --input your_video.mp4 --outdir out/runs/<run_id>`（或通过 Dashboard 选择 Tag Mode）。
- 关键输出：`TAG_CHECK.html`（首帧角点=4 且唯一 ID ≥28 视为 PASS）、`board_ids.json`、`debug/tag_metrics.csv`、`debug/tag_overlay.png`/`tag_overlay_zoom.png`/`tag_grid.png`/`tag_missing_ids.txt`。
- 可视化说明：
  - **tag_overlay.png**：warp 棋盘上叠加网格和检测到的 ID；`tag_overlay_zoom.png` 为 2× 放大。
  - **tag_grid.png**：8×8 表格写入每格 ID，方便人工核对。
  - **tag_overlays/overlay_xxxx.png**：逐帧叠加预览；缺失 ID 列表保存在 `tag_missing_ids.txt`。
- TAG_CHECK.html：内嵌首帧关键图和指标 CSV。PASS 规则：首帧角点数 >=4 且唯一 ID 数 >=28。

### 录制与摆放指引

- 机位：保持四角 ArUco 0/1/2/3 全入镜，俯拍或轻微斜角；避免强反光。
- 标签尺寸：3mm–5mm 贴纸均可；若 TAG_CHECK 报“小于期望像素”则需要更高分辨率或靠近镜头。
- 光照：使用柔光或漫反射，必要时给棋子加磨砂罩；画面过曝会自动启用阈值路径但准确度下降。
- 金属棋子反光：若棋子表面是金属或高亮材质，请使用柔光箱/白纸反射补光，尽量避免直射；可在顶部加磨砂胶贴减少反光，以免标签识别失败。

### 棋子贴码识别版（Tag 模式）

该模式假设棋盘四角贴有 ArUco 0/1/2/3 用于 warp，对每个棋子顶部贴 1-32 号小标签。流程保持本地离线，无需网络。

**一键命令（含 TAG_CHECK.html 报告）**

```bash
python scripts/run_tag_demo.py --input your_game.mp4 --outdir out/runs/demo --fps 3
```

输出目录会包含：

- `TAG_CHECK.html`：汇总 PASS/FAIL（四角==4 且首帧唯一 ID ≥28）、指标表格与关键叠加图。
- `board_ids.json`：每个稳定帧的 8x8 piece_id 矩阵（根目录 & debug 下各一份）。
- `debug/tag_metrics.csv`：逐帧 `frame_index,corners_detected,num_piece_tags,num_unique_ids,confidence_flag`，自动提示 NO_CORNERS/LOW_TAGS/DUPLICATE_IDS。
- `debug/tag_overlay_0001.png`、`tag_overlay_zoom_0001.png`、`tag_grid_0001.png`、`tag_missing_ids_0001.txt`：首帧可视化包，前 5 帧依次编号。
- `debug/tag_overlays/overlay_xxxx.png`：每帧 warp 上叠加的网格+ID 预览。
- （可选）`game.pgn`、`debug/step_confidence.json`：若解码成功则自动生成。

## 如何解读 TAG_CHECK.html / CHECK.html

- **TAG_CHECK.html（Tag 模式）**
  - PASS 规则：首帧 `corners_detected == 4` 且 `unique_ids >= 28`。
  - 页面会展示：首帧稳定图 / warp / grid overlay、前 1-5 张 tag overlay 预览、8×8 ID 表格、缺失的标签列表 (1..32)、`debug/tag_metrics.csv` 逐帧统计。
  - “Diagnostics” 区会自动给出失败原因：
    - 角点缺失：提醒重新摆放/避免裁切/检查光照；
    - 标签过少：估算像素尺寸并建议使用 5mm 标签、降低机位或补光；
    - 重复 ID：提示更换重复贴纸。
- **CHECK.html（Marker 模式）**
  - PASS 关注点：`grid_overlay.png` 与棋盘格对齐、`aruco_preview.png` 检出 4 个角标。
  - 若 FAIL，会提示角标缺失/透视失败，建议重新录制或调整机位。

**录制与摆放建议（3-5mm 标签）**

- 建议先打印 5mm 标签，熟悉后再尝试 3mm；摄像机距离越近、分辨率越高越稳定。
- 控光：避免直射高光，可在棋子顶部覆一层磨砂透明贴；保持俯拍或轻微斜角，四角 ArUco 0/1/2/3 全部入镜。
- 如果标签看起来只有几像素，TAG_CHECK 会给出 “标签过小” 警告，可提升分辨率或靠近拍摄。
- 默认 `--fps 3 --motion-threshold 0.01 --stable-duration 0.7`，如场景干扰大可适当提高阈值或缩短稳定时间。

默认 ID 映射（可在 `config/piece_id_map.json` 修改）：

- 1-8：白兵；9-10：白车；11-12：白马；13-14：白象；15：白后；16：白王。
- 17-24：黑兵；25-26：黑车；27-28：黑马；29-30：黑象；31：黑后；32：黑王。

### 网页界面（小白推荐）

最简单的使用方式，无需记忆命令行。

1. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

2. **启动网页**
   ```bash
   python scripts/start_web.py
   ```
   或者
   ```bash
   streamlit run app.py
   ```

3. **使用流程**
   - 浏览器会自动打开 http://localhost:8501
   - 点击 "Browse files" 上传视频
   - 点击 "🚀 Run Analysis"
   - 等待运行完成，直接查看 PGN 和调试图片

## Local Web Dashboard (Beginner)

最简单的入口：上传视频、点「Run」，即可在浏览器里直接看到结果和报告。

1) 安装依赖（本地离线运行）
```bash
pip install -r requirements_computer.txt
pip install -r requirements_dashboard.txt
```

2) 启动仪表盘
```bash
streamlit run dashboard_local/app.py
# 或使用一键脚本
./scripts/start_dashboard.sh
```

3) 浏览器操作
- 侧边栏自动读取 `out/runs/<run_id>` 历史任务：显示输入文件名、时间戳和 PASS/FAIL 状态，点击即可切换。
- 主界面上传 .mp4/.mov，选择模式：
  - **Marker mode**：仅四角 0/1/2/3 warp，调用 `run_debug_pipeline.py` + `make_check_report.py`，生成 CHECK.html。
  - **Tag mode**：角点 + 1..32 棋子标签，调用 `run_tag_demo.py`，生成 TAG_CHECK.html、board_ids.json、tag_metrics.csv、可下载 PGN/ZIP。
- 运行过程实时刷日志；完成后自动切换到结果页，内嵌 CHECK/TAG_CHECK 报告、关键图片，并提供 ZIP/PGN/CSV/JSON 下载。


### 前置要求

- macOS (推荐)
- Python 3.8+
- Stockfish (通过brew安装)
- ffmpeg (用于视频处理)

### 安装步骤

1. **安装系统依赖**
```bash
brew install stockfish ffmpeg
```

2. **克隆仓库**
```bash
git clone https://github.com/qyxa123/chess.git
cd chess
```

3. **创建虚拟环境**
```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
```

4. **安装Python依赖**
```bash
pip install -r requirements.txt
```

### Print Piece Tags

- 默认标签尺寸 **5mm x 5mm**（推荐），想要更隐蔽可用 `--size-mm 3` 再试。
- 将标签贴在棋子顶部，保持水平、避免反光；打印时选择 100% 真实尺寸。
- 生成打印文件：

```bash
# 生成 32 张 PNG + A4 PDF（aruco5x5_100，默认 5mm）
python scripts/generate_piece_tags.py

# 指定尺寸 3mm 或其他 family
python scripts/generate_piece_tags.py --family aruco5x5_100 --size-mm 3
```

输出目录：
- `assets/piece_tags/png/tag_01.png ... tag_32.png`
- `assets/piece_tags/piece_tags_print_sheet.pdf`（带裁切线和编号，A4）

### 使用方法

#### Debug Pipeline Quickstart（推荐先运行）

**一键测试从视频到debug输出的流程：**

```bash
# 安装依赖
pip install -r requirements_computer.txt

# 运行debug pipeline（自动查找视频文件）
python scripts/run_debug_pipeline.py --outdir out/debug_run --use_markers 1

# 或指定视频文件
python scripts/run_debug_pipeline.py --input IMG_4504.MOV --outdir out/debug_run --use_markers 1
```

**验收标准：**
1. 查看 `out/debug_run/debug/grid_overlay.png` - 网格线应该贴合棋盘格
2. 查看 `out/debug_run/debug/aruco_preview.png` - 应该看到4个标记（ID 0,1,2,3）被检测到
3. 查看 `out/debug_run/debug/warped_boards/` - 矫正后的棋盘应该是正对、无透视畸变
4. 查看 `out/debug_run/debug/stable_frames/` - 应该有多张稳定帧
5. 查看 `out/debug_run/debug/motion.csv` - 运动数据记录

**如果grid_overlay.png的网格不贴合：**
- 检查ArUco标记是否清晰可见
- 检查标记是否贴在棋盘四角（ID 0=左上, 1=右上, 2=右下, 3=左下）
- 调整拍摄角度，确保标记不被遮挡

#### 验收检查（无需看代码）

**一键生成验收报告：**

```bash
# 生成检查报告
python scripts/make_check_report.py --outdir out/debug_run

# 报告会自动生成在 out/debug_run/CHECK.html
# 双击打开即可查看
```

**或使用快捷脚本（macOS）：**

```bash
# 自动找到最近的CHECK.html并打开
./scripts/open_check.sh
```

**报告包含：**
- ✅ 基本信息（稳定帧数量、成功warp数量、失败帧列表）
- 🖼️ 关键图片（第一张稳定帧、第一张warped棋盘、grid_overlay）
- ✅ 快速判定（PASS/FAIL提示）
- 📋 Occupancy Maps（如果有）
- ⚠️ 不确定走法（如果有）

**验收标准：**
- 查看CHECK.html中的"快速判定"部分
- 如果显示"✅ PASS：网格线基本贴合格子边"，说明对齐正确
- 如果显示"❌ FAIL"，请检查ArUco标记是否正确

#### 识别8x8 Empty/Light/Dark

**从warped棋盘识别每格状态：**

```bash
python scripts/run_occupancy.py --outdir out/debug_run
```

**输出文件：**
- `board_states.json` - 每帧的8x8 labels（empty/light/dark）+ confidence
- `debug/cells_sample/` - 第一帧的64个格子切片（r{row}_c{col}.png）
- `debug/occupancy_map_0001.png` ... `occupancy_map_0005.png` - 前5帧的占用图
- `debug/confidence_map_0001.png` ... - 前5帧的置信度热力图

**验收标准：**
查看 `debug/occupancy_map_0001.png`（标准开局）：
- ✅ 第8/7行（索引7/6）应该几乎全dark（黑色）
- ✅ 第2/1行（索引1/0）应该几乎全light（白色）
- ✅ 中间四行（索引2-5）应该几乎全empty（灰色）

**方法说明（两阶段识别）：**
- **Phase A (piece vs empty)**：
  - 从第一帧中间四排(rows 2-5)采样空格，分为white_square_empty和black_square_empty
  - 计算两种底色模板（Lab均值）
  - 对每格中心patch（40%×40%）：计算color_diff和edge_score
  - 阈值自动估计：T1 = mean(color_diff_empty) + 4*std, T2 = mean(edge_score_empty) + 4*std
  - piece判定：(color_diff > T1) OR (edge_score > T2)
- **Phase B (light vs dark)**：
  - 只在piece格进行
  - 用第一帧已知布局校准：rows 0-1的piece为dark，rows 6-7的piece为light
  - 取Lab-L均值，得到阈值Tld（两均值中点）
  - L >= Tld -> light, else dark

**调试第一帧：**
```bash
python scripts/debug_first_frame.py --outdir out/debug_run --patch_ratio 0.40
```

**调试输出（debug_check/）：**
- `cells_8x8/` - 第一帧64格中心patch
- `board_first_warp.png` - 第一帧warped图
- `piece_mask.png` - 8x8 piece/empty掩码
- `diff_heatmap.png` - 8x8 color_diff热力图
- `edge_heatmap.png` - 8x8 edge_score热力图
- `occupancy_map.png` - 8x8 E/L/D结果
- `metrics.json` - T1/T2/Tld等参数和统计

**验收标准：**
- `piece_mask.png`：只有前两排+后两排为piece（白色）
- `occupancy_map.png`：上两排几乎全D，下两排几乎全L，中间几乎全E
- `metrics.json`：查看T1, T2, Tld和空格分布统计

#### 从Warped棋盘帧解码PGN

**从已矫正的棋盘图像生成PGN：**

```bash
python scripts/run_decode_pgn.py --warped_dir out/debug_run/debug/warped_boards --outdir out/pgn_decode
```

**可选参数：**
- `--uncertain_threshold 0.1`：不确定阈值（top1与top2距离差距，默认0.1）
- `--dist_threshold 2.0`：距离阈值（超过此值则不确定，默认2.0）

**输出文件：**
- `board_states.json` - 每帧的8x8 labels（empty/light/dark）+ confidence
- `game.pgn` - 推断的完整PGN（SAN格式）
- `debug/occupancy_maps/` - 每帧的占用图可视化
- `debug/diff_heatmaps/` - 相邻帧差分热力图
- `debug/uncertain_moves.json` - 低置信度步的候选走法
- `debug/cells/` - 第一帧的每格切片（用于检查分类）

**验收方式：**
1. 查看 `debug/occupancy_maps/occupancy_map_0000.png` - 应该显示标准开局（第一、二行和第七、八行有棋子）
2. 查看 `debug/cells/` - 检查每格分类是否正确
3. 打开 `game.pgn` 在网页回放中验证走法是否合理
4. 如果有多步不确定，查看 `debug/uncertain_moves.json` 检查候选走法

#### 分析单个视频（完整流程）

```bash
python -m otbreview analyze --input video.mp4 --outdir out/game1
```

**可选参数：**
- `--use_markers 1`：使用ArUco/AprilTag标记（需在棋盘四角贴标记）
- `--depth 16`：Stockfish分析深度（默认14）
- `--pv 6`：主变PV长度（默认6）

#### 监控inbox目录（自动处理）

```bash
python -m otbreview watch --inbox ~/OTBReview/inbox --outroot ~/OTBReview/output
```

当新视频放入inbox目录时，系统会自动处理。

### 输出结果

分析完成后，在输出目录中会生成：

- `game.pgn` - 标准PGN格式棋局
- `analysis.json` - 详细分析数据（每步eval、分类、PV等）
- `index.html` - 网页复盘界面（双击打开）
- `debug/` - 调试中间结果
  - `stable_frames/` - 抽取的稳定帧
  - `warped_boards/` - 透视矫正后的棋盘
  - `grid_overlay.png` - 网格覆盖图
  - `cells/` - 每格切片
  - `step_confidence.json` - 每步置信度

## 网页复盘功能

打开 `index.html` 后，你可以：

- ✅ **棋盘回放**：点击走法列表跳转到任意步
- ✅ **Eval Bar + Graph**：查看评估值变化曲线
- ✅ **走法分类**：Best/Good/Inaccuracy/Mistake/Blunder/Book
- ✅ **关键走法**：Next按钮只跳转关键点
- ✅ **Show Follow-up**：展示Stockfish PV（3-6步）
- ✅ **纠错功能**：低置信度走法可手动选择正确走法

## 参数调优指南

### 视频拍摄建议

- **固定俯拍**：iPhone固定位置，垂直俯拍棋盘
- **光照均匀**：避免强烈阴影和反光
- **棋盘清晰**：确保棋盘边界清晰可见
- **标记增强**（可选）：在棋盘四角贴ArUco/AprilTag标记可提高定位精度

### 可调参数

在代码中可调整的参数：

- **motion_threshold** (extract.py)：运动检测阈值，默认0.01
  - 值越小，对运动越敏感
- **stable_duration** (extract.py)：稳定持续时间（秒），默认0.5
  - 值越大，要求稳定时间越长
- **分类阈值** (classify.py)：Best/Good/Inaccuracy/Mistake/Blunder的cp loss阈值

## 项目结构

```
chess/
├── otbreview/              # 主包
│   ├── __init__.py
│   ├── cli.py              # 统一CLI接口
│   ├── pipeline/           # 处理流程
│   │   ├── extract.py      # 稳定帧抽取
│   │   ├── board_detect.py # 棋盘定位
│   │   ├── pieces.py       # 棋子识别
│   │   ├── decode.py       # 合法性约束解码
│   │   ├── pgn.py          # PGN生成
│   │   ├── analyze.py      # Stockfish分析
│   │   ├── classify.py     # 走法分类
│   │   ├── keymoves.py     # 关键走法识别
│   │   ├── main.py         # 主流程
│   │   └── watcher.py      # 目录监控
│   └── web/                # 网页生成
│       └── generate.py     # HTML生成
├── scripts/                # 工具脚本
├── tests/                  # 测试
├── requirements.txt        # Python依赖
└── README.md              # 本文档
```

## 开发状态

### 已完成（阶段0）
- ✅ 项目结构重构
- ✅ 统一CLI接口
- ✅ 模块化设计

### 进行中（阶段1-3）
- 🚧 稳定帧抽取（基础实现）
- 🚧 棋盘定位（基础实现，ArUco待完善）
- 🚧 棋子识别（基础实现）
- 🚧 合法性约束解码（核心算法）
- 🚧 网页复盘（基础框架）

### 待完善
- ⏳ ArUco/AprilTag完整支持
- ⏳ 更精确的棋子识别
- ⏳ 完整的网页复盘功能（棋盘渲染、PV播放、Retry等）
- ⏳ 纠错机制的前端实现

## 贡献

欢迎提交Issue和Pull Request！

## 许可证

[待定]
