#!/usr/bin/env python3
"""
生成棋子顶部贴纸 (ArUco / AprilTag)
用于打印并贴在棋子顶部，实现ID识别
"""

import argparse
from pathlib import Path

import cv2
import numpy as np
from fpdf import FPDF


def generate_tags(family='aruco5x5_100', size_mm=5, start_id=1, count=32, output_dir='assets/piece_tags'):
    """
    生成指定系列的标签
    默认使用 AprilTag 36h11 (更小、抗干扰强)
    也可选 ArUco Original / 4x4_50 等
    """
    output_path = Path(output_dir)
    png_dir = output_path / "png"
    png_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Generating {count} tags ({family}) starting from ID {start_id}...")

    # 初始化字典
    if '5x5' in family:
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
    elif '6x6' in family:
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
    elif 'apriltag' in family.lower():
        try:
            dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        except AttributeError:
            print("Warning: DICT_APRILTAG_36h11 not found, falling back to 5x5_100")
            dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
    else:
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

    # 生成每个ID的图片
    tag_files = []
    pixel_size = 200  # 高分辨率用于打印
    
    for i in range(count):
        tag_id = start_id + i
        img = np.zeros((pixel_size, pixel_size), dtype=np.uint8)
        img = cv2.aruco.generateImageMarker(dictionary, tag_id, pixel_size, img, 1)
        
        filename = png_dir / f"tag_{tag_id:02d}.png"
        cv2.imwrite(str(filename), img)
        tag_files.append((tag_id, str(filename)))
        print(f"  Saved {filename}")

    # 生成PDF排版
    pdf_path = output_path / "piece_tags_print_sheet.pdf"
    create_pdf_sheet(tag_files, pdf_path, size_mm)
    print(f"\nPDF sheet generated: {pdf_path}")
    print(f"Print this on A4 paper at 100% scale.")
    print(f"Each tag will be {size_mm}mm x {size_mm}mm.")

def create_pdf_sheet(tag_files, output_path, size_mm):
    """
    将标签排版到A4纸上
    """
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", size=8)
    
    margin_x = 10
    margin_y = 10
    spacing = 2 # 间距mm
    
    # 计算行列
    # A4: 210 x 297 mm
    x = margin_x
    y = margin_y
    
    pdf.cell(0, 10, f"Chess Piece Tags (Size: {size_mm}mm) - Print at 100% Scale", ln=True)
    y += 10
    
    for tag_id, img_path in tag_files:
        # 绘制标签图片
        pdf.image(img_path, x, y, w=size_mm, h=size_mm)
        
        # 绘制边框（方便剪裁）
        pdf.rect(x, y, size_mm, size_mm)
        # 外围裁切参考框
        pdf.rect(x - 0.5, y - 0.5, size_mm + 1, size_mm + 1, style='D')

        # 绘制ID编号（下方）
        pdf.text(x, y + size_mm + 3, f"ID {tag_id}")
        
        # 移动坐标
        x += size_mm + spacing + 5 # 额外留白方便剪
        
        if x > 190: # 换行
            x = margin_x
            y += size_mm + spacing + 8

    pdf.output(str(output_path))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate ArUco/AprilTag tags for chess pieces")
    parser.add_argument("--family", default="aruco5x5_100", help="Tag family (aruco5x5_100, apriltag36h11, etc)")
    parser.add_argument("--size-mm", type=int, default=5, help="Physical size of the tag in mm (recommend 5 then try 3)")
    parser.add_argument("--count", type=int, default=32, help="Number of tags to generate (default 32 for full set)")

    args = parser.parse_args()

    generate_tags(family=args.family, size_mm=args.size_mm, count=args.count)
