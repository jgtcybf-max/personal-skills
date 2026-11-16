"""Image OCR tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import image_ocr


def test_ocr_image_converts_to_png_invokes_tesseract_and_cleans_text(monkeypatch, tmp_path):
    image_path = tmp_path / "note.jpg"
    Image.new("RGB", (8, 8), "white").save(image_path, format="WEBP")
    calls = []

    def fake_run(args, capture_output, check):
        calls.append((args, capture_output, check))
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=" 第一行 \n\n第一行\n 第二行  \n".encode(),
            stderr=b"",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = image_ocr.ocr_image(str(image_path), lang="chi_sim+eng", tesseract_cmd="tesseract")

    assert calls == [
        (
            [calls[0][0][0], calls[0][0][1], "stdout", "-l", "chi_sim+eng", "--psm", "6"],
            True,
            False,
        )
    ]
    assert calls[0][0][0] == "tesseract"
    assert calls[0][0][1].endswith(".png")
    assert calls[0][0][1] != str(image_path)
    assert result == "第一行\n第二行"


def test_ocr_image_decodes_non_utf8_stderr_without_unicode_error(monkeypatch, tmp_path):
    image_path = tmp_path / "note.jpg"
    Image.new("RGB", (8, 8), "white").save(image_path, format="WEBP")

    def fake_run(args, capture_output, check):
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout=b"",
            stderr=b"Image file RIFF\xcc\xbd\x02 cannot be read!",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    try:
        image_ocr.ocr_image(str(image_path))
    except RuntimeError as e:
        assert "Image file" in str(e)
        assert "cannot be read" in str(e)
    else:
        raise AssertionError("Expected RuntimeError")


def test_parse_ocr_content_merges_images_and_removes_adjacent_duplicates():
    result = image_ocr.parse_ocr_content([" 标题\n标题\n正文 ", "", "正文\n结尾"])

    assert result == "标题\n正文\n结尾"
