# OTBReview - 实体棋盘视频分析系统

将实体棋盘视频转换为PGN，并使用Stockfish进行复盘分析。

## 功能特性

- 📹 **视频解析**：自动从视频中抽取稳定局面帧
- 🎯 **棋盘定位**：支持ArUco/AprilTag标记或纯视觉检测
- ♟️ **走法识别**：基于合法性约束的解码算法
- 🧠 **Stockfish分析**：本地离线分析，无需会员
- 📊 **可视化复盘**：仿chess.com风格的网页复盘界面
- 🔧 **纠错机制**：低置信度走法可手动修正

## 快速开始

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
