#!/usr/bin/env python
import argparse
from pathlib import Path

import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment
from PIL import Image as PILImage


def sorted_images(folder: Path, prefix: str):
    files = []
    for pattern in (f"{prefix}_*.*", f"{prefix}*.*"):
        files.extend(folder.glob(pattern))
    seen = []
    for path in sorted(files):
        if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and path not in seen:
            seen.append(path)
    return seen


def find_header_column(ws, header: str):
    for cell in ws[1]:
        if str(cell.value or "").strip() == header:
            return cell.column
    return None


def px_to_excel_width(px: int) -> float:
    return max(8, (px - 5) / 7)


def convert_for_excel(src: Path, dst: Path):
    with PILImage.open(src) as im:
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.convert("RGB").save(dst, "PNG")
        return im.size


def main():
    parser = argparse.ArgumentParser(description="Insert shoe main/detail images into one Excel template column.")
    parser.add_argument("--template", required=True, help="Input .xlsx template.")
    parser.add_argument("--images", required=True, help="Folder containing main_images and detail_images.")
    parser.add_argument("--output", required=True, help="Output .xlsx path.")
    parser.add_argument("--column-header", default="苏茵茵", help="Header text in row 1 to fill.")
    parser.add_argument("--main-count", type=int, default=5)
    parser.add_argument("--main-start-row", type=int, default=2)
    parser.add_argument("--detail-start-row", type=int, default=7)
    parser.add_argument("--max-width-px", type=int, default=300)
    parser.add_argument("--min-height-px", type=int, default=120)
    parser.add_argument("--max-height-px", type=int, default=980)
    args = parser.parse_args()

    template = Path(args.template)
    image_root = Path(args.images)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.load_workbook(template)
    ws = wb.active
    col = find_header_column(ws, args.column_header)
    if col is None:
        raise SystemExit(f"Column header not found in row 1: {args.column_header}")

    # Remove prior images anchored in the target column only.
    retained = []
    for img in getattr(ws, "_images", []):
        try:
            anchor_col = img.anchor._from.col + 1
        except Exception:
            anchor_col = None
        if anchor_col != col:
            retained.append(img)
    ws._images = retained

    for row in range(2, ws.max_row + 1):
        cell = ws.cell(row, col)
        cell.value = None
        cell.alignment = Alignment(horizontal="center", vertical="center")

    main_files = sorted_images(image_root / "main_images", "main")[: args.main_count]
    detail_files = sorted_images(image_root / "detail_images", "detail")

    items = []
    for idx, path in enumerate(main_files):
        items.append((args.main_start_row + idx, path, "main"))
    for idx, path in enumerate(detail_files):
        row = args.detail_start_row + idx
        if row <= ws.max_row:
            items.append((row, path, "detail"))

    converted_dir = output.parent / f"{output.stem}_converted_images"
    ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = px_to_excel_width(args.max_width_px + 20)

    for row, image_path, kind in items:
        converted = converted_dir / f"{kind}_{row:03d}.png"
        width, height = convert_for_excel(image_path, converted)
        scale = args.max_width_px / width
        display_width = args.max_width_px
        display_height = max(args.min_height_px, min(int(height * scale), args.max_height_px))

        xl_img = XLImage(str(converted))
        xl_img.width = display_width
        xl_img.height = display_height
        ws.add_image(xl_img, f"{openpyxl.utils.get_column_letter(col)}{row}")
        ws.row_dimensions[row].height = display_height * 0.75 + 8

    wb.save(output)
    print(f"Saved: {output}")
    print(f"Inserted main images: {len(main_files)}")
    print(f"Inserted detail images: {min(len(detail_files), max(0, ws.max_row - args.detail_start_row + 1))}")


if __name__ == "__main__":
    main()
