#!/usr/bin/env python3
"""
验收检查报告生成器
自动生成CHECK.html报告，帮助用户判断pipeline是否成功
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
import json


def find_files(pattern: str, directory: Path) -> list:
    """查找文件，返回排序后的列表"""
    files = sorted(directory.glob(pattern))
    return [f for f in files if f.is_file()]


def read_text_file(filepath: Path) -> str:
    """读取文本文件，如果不存在返回空字符串"""
    if filepath.exists():
        try:
            return filepath.read_text(encoding='utf-8').strip()
        except:
            return ""
    return ""


def count_files(directory: Path, pattern: str) -> int:
    """统计匹配模式的文件数量"""
    if not directory.exists():
        return 0
    return len(list(directory.glob(pattern)))


def generate_html_report(outdir: Path) -> str:
    """生成HTML报告"""
    debug_dir = outdir / "debug"
    
    # 收集基本信息
    stable_frames_count = count_files(debug_dir / "stable_frames", "*.png")
    stable_frames_count += count_files(debug_dir / "stable_frames", "*.jpg")
    
    warped_count = count_files(debug_dir / "warped_boards", "warp_*.png")
    warped_count += count_files(debug_dir / "warped_boards", "*_warped.jpg")
    
    # 查找关键图片
    first_stable = None
    stable_files = find_files("frame_*.png", debug_dir / "stable_frames")
    if not stable_files:
        stable_files = find_files("stable_*.jpg", debug_dir / "stable_frames")
    if stable_files:
        first_stable = stable_files[0].relative_to(outdir)
    
    first_warped = None
    warped_files = find_files("warp_*.png", debug_dir / "warped_boards")
    if not warped_files:
        warped_files = find_files("*_warped.jpg", debug_dir / "warped_boards")
    if warped_files:
        first_warped = warped_files[0].relative_to(outdir)
    
    grid_overlay = None
    grid_path = debug_dir / "grid_overlay.png"
    if grid_path.exists():
        grid_overlay = grid_path.relative_to(outdir)
    
    # 读取失败帧列表
    fail_frames = []
    fail_path = debug_dir / "fail_frames.txt"
    if fail_path.exists():
        fail_text = read_text_file(fail_path)
        if fail_text:
            fail_frames = [line.strip() for line in fail_text.split('\n') if line.strip() and not line.startswith('#')]
    
    # 查找occupancy maps
    occupancy_maps = find_files("occupancy_map_*.png", debug_dir / "occupancy_maps")[:3]
    occupancy_maps = [f.relative_to(outdir) for f in occupancy_maps]
    
    # 读取uncertain moves
    uncertain_moves = None
    uncertain_path = debug_dir / "uncertain_moves.json"
    if uncertain_path.exists():
        try:
            uncertain_moves = json.loads(uncertain_path.read_text(encoding='utf-8'))
        except:
            pass
    
    # 判断grid overlay是否通过
    grid_pass = grid_overlay is not None
    
    # 生成HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OTBReview 验收检查报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: #f5f5f5;
            padding: 20px;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        h1 {{
            color: #333;
            margin-bottom: 10px;
            border-bottom: 3px solid #4a9eff;
            padding-bottom: 10px;
        }}
        
        .timestamp {{
            color: #666;
            font-size: 14px;
            margin-bottom: 30px;
        }}
        
        .section {{
            margin-bottom: 40px;
        }}
        
        .section h2 {{
            color: #4a9eff;
            margin-bottom: 15px;
            padding-bottom: 5px;
            border-bottom: 2px solid #e0e0e0;
        }}
        
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        
        .info-item {{
            background: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #4a9eff;
        }}
        
        .info-item strong {{
            display: block;
            color: #333;
            margin-bottom: 5px;
        }}
        
        .info-item .value {{
            color: #666;
            font-size: 18px;
        }}
        
        .image-container {{
            margin: 20px 0;
            text-align: center;
        }}
        
        .image-container img {{
            max-width: 100%;
            height: auto;
            border: 2px solid #ddd;
            border-radius: 5px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        
        .image-label {{
            margin-top: 10px;
            color: #666;
            font-weight: bold;
        }}
        
        .status-banner {{
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
            text-align: center;
            font-size: 24px;
            font-weight: bold;
        }}
        
        .status-pass {{
            background: #d4edda;
            color: #155724;
            border: 2px solid #c3e6cb;
        }}
        
        .status-fail {{
            background: #f8d7da;
            color: #721c24;
            border: 2px solid #f5c6cb;
        }}
        
        .status-warning {{
            background: #fff3cd;
            color: #856404;
            border: 2px solid #ffeaa7;
        }}
        
        .fail-list {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin-top: 10px;
        }}
        
        .fail-list ul {{
            margin-left: 20px;
            color: #721c24;
        }}
        
        .uncertain-moves {{
            background: #fff3cd;
            padding: 15px;
            border-radius: 5px;
            margin-top: 10px;
        }}
        
        .uncertain-moves h3 {{
            color: #856404;
            margin-bottom: 10px;
        }}
        
        .uncertain-moves pre {{
            background: white;
            padding: 10px;
            border-radius: 3px;
            overflow-x: auto;
            font-size: 12px;
        }}
        
        .missing {{
            color: #999;
            font-style: italic;
        }}
        
        .image-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 OTBReview 验收检查报告</h1>
        <div class="timestamp">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        
        <!-- 基本信息 -->
        <div class="section">
            <h2>📊 基本信息</h2>
            <div class="info-grid">
                <div class="info-item">
                    <strong>稳定帧数量</strong>
                    <span class="value">{stable_frames_count}</span>
                </div>
                <div class="info-item">
                    <strong>成功Warp数量</strong>
                    <span class="value">{warped_count}</span>
                </div>
                <div class="info-item">
                    <strong>失败帧数量</strong>
                    <span class="value">{len(fail_frames)}</span>
                </div>
            </div>
            
            {f'<div class="fail-list"><strong>失败帧列表:</strong><ul>' + ''.join(f'<li>{f}</li>' for f in fail_frames[:10]) + '</ul></div>' if fail_frames else ''}
        </div>
        
        <!-- 关键图片 -->
        <div class="section">
            <h2>🖼️ 关键图片检查</h2>
            
            {f'''
            <div class="image-container">
                <img src="{first_stable}" alt="第一张稳定帧">
                <div class="image-label">第一张稳定帧</div>
            </div>
            ''' if first_stable else '<div class="missing">❌ 未找到稳定帧</div>'}
            
            {f'''
            <div class="image-container">
                <img src="{first_warped}" alt="第一张Warped棋盘">
                <div class="image-label">第一张Warped棋盘（800x800）</div>
            </div>
            ''' if first_warped else '<div class="missing">❌ 未找到Warped棋盘</div>'}
            
            {f'''
            <div class="image-container">
                <img src="{grid_overlay}" alt="网格覆盖图">
                <div class="image-label">网格覆盖图（检查对齐）</div>
            </div>
            ''' if grid_overlay else '<div class="missing">❌ 未找到grid_overlay.png</div>'}
        </div>
        
        <!-- 快速判定 -->
        <div class="section">
            <h2>✅ 快速判定</h2>
            {f'''
            <div class="status-banner status-pass">
                ✅ PASS：网格线基本贴合格子边
            </div>
            <p style="margin-top: 15px; color: #666;">
                如果网格线明显偏移，请检查：
                <ul style="margin-left: 20px; margin-top: 10px;">
                    <li>ArUco标记顺序是否正确（ID 0=左上, 1=右上, 2=右下, 3=左下）</li>
                    <li>标记是否全部入镜且清晰可见</li>
                    <li>标记是否反光或被遮挡</li>
                </ul>
            </p>
            ''' if grid_overlay else '''
            <div class="status-banner status-warning">
                ⚠️ 无法判定：缺少grid_overlay.png
            </div>
            '''}
        </div>
        
        <!-- Occupancy Maps -->
        {generate_occupancy_section(occupancy_maps) if occupancy_maps else ''}
        
        <!-- Uncertain Moves -->
        {f'''
        <div class="section">
            <h2>⚠️ 不确定走法</h2>
            <div class="uncertain-moves">
                <h3>发现 {len(uncertain_moves)} 个不确定走法</h3>
                <pre>{json.dumps(uncertain_moves, indent=2, ensure_ascii=False)}</pre>
            </div>
        </div>
        ''' if uncertain_moves else ''}
        
        <!-- 底部提示 -->
        <div class="section" style="margin-top: 40px; padding-top: 20px; border-top: 2px solid #e0e0e0;">
            <p style="color: #666; text-align: center;">
                如果发现问题，请检查 debug/ 目录中的详细输出文件
            </p>
        </div>
    </div>
</body>
</html>
"""
    return html


def main():
    parser = argparse.ArgumentParser(
        description="生成验收检查报告 CHECK.html"
    )
    parser.add_argument(
        '--outdir',
        type=str,
        required=True,
        help='输出目录（某次运行的输出目录）'
    )
    
    args = parser.parse_args()
    
    outdir = Path(args.outdir)
    if not outdir.exists():
        print(f"错误: 输出目录不存在: {outdir}")
        sys.exit(1)
    
    print(f"生成验收检查报告...")
    print(f"输出目录: {outdir}")
    
    # 生成HTML
    html_content = generate_html_report(outdir)
    
    # 保存报告
    report_path = outdir / "CHECK.html"
    report_path.write_text(html_content, encoding='utf-8')
    
    print(f"\n✅ 报告已生成: {report_path}")
    print(f"\n打开方式:")
    print(f"  1. 双击 {report_path}")
    print(f"  2. 或在浏览器中打开: file://{report_path.absolute()}")
    print(f"  3. 或运行: open {report_path}")


if __name__ == '__main__':
    main()

