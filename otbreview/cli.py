#!/usr/bin/env python3
"""
OTBReview 统一CLI接口
"""

import argparse
import sys
import os
from pathlib import Path
from typing import Optional


def analyze_command(args):
    """分析单个视频文件"""
    from otbreview.pipeline.main import analyze_video
    
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误：视频文件不存在: {input_path}")
        sys.exit(1)
    
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    
    print(f"开始分析视频: {input_path}")
    print(f"输出目录: {outdir}")
    print(f"使用标记: {args.use_markers}")
    print(f"分析深度: {args.depth}")
    print(f"PV长度: {args.pv}")
    
    try:
        analyze_video(
            video_path=str(input_path),
            outdir=str(outdir),
            use_markers=bool(args.use_markers),
            depth=args.depth,
            pv_length=args.pv
        )
        print(f"\n分析完成！结果保存在: {outdir}")
        print(f"打开 {outdir / 'index.html'} 查看复盘")
    except Exception as e:
        print(f"分析失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def watch_command(args):
    """监控inbox目录，自动处理新视频"""
    from otbreview.pipeline.watcher import watch_inbox
    
    inbox = Path(args.inbox)
    outroot = Path(args.outroot)
    
    if not inbox.exists():
        print(f"错误：inbox目录不存在: {inbox}")
        sys.exit(1)
    
    outroot.mkdir(parents=True, exist_ok=True)
    
    print(f"监控目录: {inbox}")
    print(f"输出根目录: {outroot}")
    print("按 Ctrl+C 停止监控...")
    
    try:
        watch_inbox(
            inbox_dir=str(inbox),
            outroot_dir=str(outroot),
            use_markers=bool(args.use_markers),
            depth=args.depth,
            pv_length=args.pv
        )
    except KeyboardInterrupt:
        print("\n监控已停止")
    except Exception as e:
        print(f"监控失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="OTBReview - 实体棋盘视频分析系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 分析单个视频
  python -m otbreview analyze --input video.mp4 --outdir out/game1

  # 分析视频（使用ArUco标记）
  python -m otbreview analyze --input video.mp4 --outdir out/game1 --use_markers 1

  # 监控inbox目录
  python -m otbreview watch --inbox ~/OTBReview/inbox --outroot ~/OTBReview/output
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # analyze 命令
    analyze_parser = subparsers.add_parser('analyze', help='分析单个视频文件')
    analyze_parser.add_argument('--input', '-i', required=True, help='输入视频文件路径')
    analyze_parser.add_argument('--outdir', '-o', required=True, help='输出目录')
    analyze_parser.add_argument('--use_markers', type=int, default=0, 
                               help='是否使用ArUco/AprilTag标记 (0=否, 1=是)')
    analyze_parser.add_argument('--depth', type=int, default=14, 
                               help='Stockfish分析深度 (默认: 14)')
    analyze_parser.add_argument('--pv', type=int, default=6, 
                               help='主变PV长度 (默认: 6)')
    analyze_parser.set_defaults(func=analyze_command)
    
    # watch 命令
    watch_parser = subparsers.add_parser('watch', help='监控inbox目录，自动处理新视频')
    watch_parser.add_argument('--inbox', required=True, help='监控的inbox目录路径')
    watch_parser.add_argument('--outroot', required=True, help='输出根目录')
    watch_parser.add_argument('--use_markers', type=int, default=0,
                              help='是否使用ArUco/AprilTag标记 (0=否, 1=是)')
    watch_parser.add_argument('--depth', type=int, default=14,
                              help='Stockfish分析深度 (默认: 14)')
    watch_parser.add_argument('--pv', type=int, default=6,
                              help='主变PV长度 (默认: 6)')
    watch_parser.set_defaults(func=watch_command)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()

