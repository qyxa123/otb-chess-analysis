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

## 快速开始

### 棋子贴码识别版（Tag 模式）

该模式假设棋盘四角贴有ArUco 0/1/2/3用于warp对齐，棋子顶部贴1-32号小tag用于定位身份。

流程概览：

1. **稳定帧抽取**：沿用现有`extract_stable_frames`，保持fps与阈值逻辑不变。
2. **棋盘warp**：在每个稳定帧上检测0-3号ArUco四角，warp到800x800。
3. **标签检测**：在warp图上检测1-32号标签，过滤太小的框并输出中心坐标与ID；同一格子/同一ID冲突时取面积更大的检测。
4. **落格映射**：按 `col=floor(x/(size/8)), row=floor(y/(size/8))` 生成8x8的piece_id矩阵，保存为`debug/board_ids.json`。
5. **可视化**：在`debug/tag_overlays/`输出每帧`overlay_xxxx.png`，`debug/tag_overlay.png`为第一帧示例，同时保存8x8矩阵。
6. **走法解码**：利用`config/piece_id_map.json`中的ID→棋子映射，用python-chess比对相邻两帧的piece_id变化，自动推断走法（含吃子、易位、升变）。
7. **输出**：生成`game.pgn`，`analysis.json`以及带「Tag Overlay Viewer」的网页复盘（`index.html`）。

默认ID映射（可在`config/piece_id_map.json`里修改）：

- 1-8：白方a2-h2兵；9-10：白车（a1/h1）；11-12：白马（b1/g1）；13-14：白象（c1/f1）；15：后；16：王。
- 17-24：黑方a7-h7兵；25-26：黑车（a8/h8）；27-28：黑马（b8/g8）；29-30：黑象（c8/f8）；31：后；32：王。

网页复盘新增「Tag Overlay Viewer」页签：可选择帧查看`overlay`叠加图和8x8 piece_id表格，并在侧边展示ID映射，方便核对检测结果。

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
