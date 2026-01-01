# 手机端/采集端

## 功能
- **视频录制**：录制象棋对局视频
- **自动传输**：将录制的视频自动传输到服务器
- **触发分析**：请求服务器对视频进行分析

## 依赖
- Python 3.6+
- ffmpeg (用于视频录制)
- requests (用于网络通信)

## 安装
```bash
pip install -r requirements_mobile.txt
```

## 使用
```bash
python mobile_capture.py
```

## 配置
在 `mobile_capture.py` 中修改以下配置：
- `server_url`：服务器地址
- `recording_dir`：录制文件保存目录