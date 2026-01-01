#!/usr/bin/env python3
"""
监控inbox目录，自动处理新视频
"""

import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from otbreview.pipeline.main import analyze_video


class VideoHandler(FileSystemEventHandler):
    """处理新视频文件"""
    
    def __init__(self, outroot_dir: str, use_markers: bool, depth: int, pv_length: int):
        self.outroot_dir = Path(outroot_dir)
        self.use_markers = use_markers
        self.depth = depth
        self.pv_length = pv_length
        self.processed = set()
    
    def on_created(self, event):
        """文件创建事件"""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        # 只处理视频文件
        if file_path.suffix.lower() not in ['.mp4', '.mov', '.avi', '.mkv']:
            return
        
        # 避免重复处理
        if str(file_path) in self.processed:
            return
        
        # 等待文件写入完成
        time.sleep(2)
        
        if not file_path.exists():
            return
        
        print(f"\n检测到新视频: {file_path.name}")
        
        # 生成输出目录名
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        outdir = self.outroot_dir / f"game_{timestamp}"
        
        try:
            analyze_video(
                video_path=str(file_path),
                outdir=str(outdir),
                use_markers=self.use_markers,
                depth=self.depth,
                pv_length=self.pv_length
            )
            self.processed.add(str(file_path))
            print(f"处理完成: {outdir}")
        except Exception as e:
            print(f"处理失败: {e}")
            import traceback
            traceback.print_exc()


def watch_inbox(
    inbox_dir: str,
    outroot_dir: str,
    use_markers: bool = False,
    depth: int = 14,
    pv_length: int = 6
) -> None:
    """
    监控inbox目录，自动处理新视频
    
    Args:
        inbox_dir: 监控的inbox目录
        outroot_dir: 输出根目录
        use_markers: 是否使用标记
        depth: Stockfish深度
        pv_length: PV长度
    """
    inbox_path = Path(inbox_dir)
    if not inbox_path.exists():
        raise ValueError(f"inbox目录不存在: {inbox_dir}")
    
    event_handler = VideoHandler(
        outroot_dir=outroot_dir,
        use_markers=use_markers,
        depth=depth,
        pv_length=pv_length
    )
    
    observer = Observer()
    observer.schedule(event_handler, str(inbox_path), recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    
    observer.join()

