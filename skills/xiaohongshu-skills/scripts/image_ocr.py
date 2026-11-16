"""图片 OCR 与文本清理。"""

from __future__ import annotations

import os
import subprocess
import tempfile
from contextlib import contextmanager, suppress

from PIL import Image


def _clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    previous = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line == previous:
            continue
        lines.append(line)
        previous = line
    return lines


def _decode_output(data: bytes | str) -> str:
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")


@contextmanager
def _prepared_ocr_image(image_path: str):
    tmp_path = ""
    try:
        with Image.open(image_path) as image:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            image.save(tmp_path, format="PNG")
        yield tmp_path
    finally:
        if tmp_path:
            with suppress(FileNotFoundError):
                os.unlink(tmp_path)


def ocr_image(
    image_path: str,
    lang: str = "chi_sim+eng",
    tesseract_cmd: str = "tesseract",
) -> str:
    """使用本地 Tesseract 识别单张图片。"""
    with _prepared_ocr_image(image_path) as prepared_path:
        cmd = [tesseract_cmd, prepared_path, "stdout", "-l", lang, "--psm", "6"]
        try:
            result = subprocess.run(cmd, capture_output=True, check=False)
        except FileNotFoundError as e:
            raise RuntimeError(f"找不到 tesseract 命令: {tesseract_cmd}") from e

    if result.returncode != 0:
        error = _decode_output(result.stderr).strip() or "OCR 执行失败"
        raise RuntimeError(error)

    return "\n".join(_clean_lines(_decode_output(result.stdout)))


def ocr_images(
    image_paths: list[str],
    lang: str = "chi_sim+eng",
    tesseract_cmd: str = "tesseract",
) -> list[dict[str, str]]:
    """按顺序识别多张图片。"""
    return [
        {"path": path, "text": ocr_image(path, lang=lang, tesseract_cmd=tesseract_cmd)}
        for path in image_paths
    ]


def parse_ocr_content(texts: list[str]) -> str:
    """合并多张图片 OCR 文本，并去除空行与相邻重复行。"""
    return "\n".join(_clean_lines("\n".join(texts)))
