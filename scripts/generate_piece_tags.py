"""Generate printable AprilTag/ArUco stickers for chess pieces.

This script creates 32 tag images (PNG) and a printable PDF sheet laid out on an
A4 page. Tags are numbered to match chess pieces:

- White pieces: IDs 1-16
- Black pieces: IDs 17-32

By default it uses the AprilTag 36h11 dictionary bundled with OpenCV, but ArUco
4x4 or 5x5 dictionaries can also be selected.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


DEFAULT_TAG_SIZE_MM = 5.0
PDF_MARGIN_MM = 15.0
TAG_BORDER_MM = 0.25  # visible cut line border around the tag itself
LABEL_GAP_MM = 1.0
LABEL_WIDTH_MM = 8.0
PADDING_MM = 2.0


def get_dictionary(family: str) -> cv2.aruco_Dictionary:
    """Return the requested ArUco/AprilTag dictionary."""

    family = family.lower()
    if family == "apriltag":
        return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    if family == "aruco4x4":
        return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)
    if family == "aruco5x5":
        return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)

    raise ValueError(f"Unsupported family '{family}'. Choose apriltag, aruco4x4, or aruco5x5.")


def generate_tag_images(dictionary: cv2.aruco_Dictionary, output_dir: Path, marker_px: int) -> list[Path]:
    """Generate numbered tag PNG files and return their paths."""

    output_dir.mkdir(parents=True, exist_ok=True)
    tag_paths: list[Path] = []

    for tag_id in range(1, 33):
        image = cv2.aruco.drawMarker(dictionary, tag_id - 1, marker_px)
        padded = cv2.copyMakeBorder(image, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
        path = output_dir / f"tag_{tag_id:02d}.png"
        cv2.imwrite(str(path), padded)
        tag_paths.append(path)

    return tag_paths


def layout_pdf(tag_paths: list[Path], pdf_path: Path, tag_size_mm: float) -> None:
    """Lay out tags on an A4 PDF with labels and cut lines."""

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    page_width, page_height = A4
    tag_size_pt = tag_size_mm * mm
    margin_pt = PDF_MARGIN_MM * mm
    padding_pt = PADDING_MM * mm
    label_gap_pt = LABEL_GAP_MM * mm
    label_width_pt = LABEL_WIDTH_MM * mm
    border_offset_pt = TAG_BORDER_MM * mm

    cell_width = padding_pt * 2 + tag_size_pt + label_gap_pt + label_width_pt
    cell_height = padding_pt * 2 + tag_size_pt

    cols = max(1, int((page_width - 2 * margin_pt) // cell_width))
    rows = max(1, int((page_height - 2 * margin_pt) // cell_height))

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    c.setTitle("Chess Piece Tags")
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)

    x_start = margin_pt
    y_start = page_height - margin_pt - cell_height

    col_idx = 0
    row_idx = 0

    for idx, tag_path in enumerate(tag_paths, start=1):
        if col_idx >= cols:
            col_idx = 0
            row_idx += 1
        if row_idx >= rows:
            c.showPage()
            c.setFont("Helvetica", 8)
            row_idx = 0
            col_idx = 0

        x = x_start + col_idx * cell_width
        y = y_start - row_idx * cell_height

        img_x = x + padding_pt
        img_y = y + padding_pt

        c.drawImage(str(tag_path), img_x, img_y, width=tag_size_pt, height=tag_size_pt, preserveAspectRatio=True, mask="auto")

        c.setLineWidth(0.5)
        c.rect(img_x - border_offset_pt, img_y - border_offset_pt, tag_size_pt + 2 * border_offset_pt, tag_size_pt + 2 * border_offset_pt)

        label_x = img_x + tag_size_pt + label_gap_pt
        label_y = img_y + (tag_size_pt / 2.0) - 3
        c.drawString(label_x, label_y, f"{idx:02d}")

        col_idx += 1

    c.save()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate printable AprilTag/ArUco stickers for chess pieces.")
    parser.add_argument(
        "--family",
        default="apriltag",
        choices=["apriltag", "aruco4x4", "aruco5x5"],
        help="Tag family to use (default: apriltag).",
    )
    parser.add_argument(
        "--tag-size-mm",
        type=float,
        default=DEFAULT_TAG_SIZE_MM,
        help="Printed tag size in millimeters (default: 5).",
    )
    parser.add_argument(
        "--marker-pixels",
        type=int,
        default=400,
        help="Pixel width/height for generated tag PNGs (default: 400).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/piece_tags"),
        help="Output directory for PNGs and PDF (default: assets/piece_tags).",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dictionary = get_dictionary(args.family)

    png_dir = Path(args.output_dir) / "png"
    tag_paths = generate_tag_images(dictionary, png_dir, args.marker_pixels)

    pdf_path = Path(args.output_dir) / "piece_tags_print_sheet.pdf"
    layout_pdf(tag_paths, pdf_path, args.tag_size_mm)

    print(f"Generated {len(tag_paths)} tags in {png_dir}")
    print(f"PDF sheet saved to {pdf_path}")


if __name__ == "__main__":
    main()
