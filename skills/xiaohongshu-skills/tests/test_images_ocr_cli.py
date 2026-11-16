"""images-ocr CLI tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cli
import image_downloader
import image_ocr
import xhs.feed_detail


class DummyBrowser:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_images_ocr_downloads_images_and_outputs_parsed_content(monkeypatch):
    browser = DummyBrowser()
    page = object()
    captured: dict = {}

    detail = SimpleNamespace(
        note=SimpleNamespace(
            image_list=[
                SimpleNamespace(url_default="https://img.example/a.jpg", url_pre=""),
                SimpleNamespace(url_default="https://img.example/b.jpg", url_pre=""),
            ]
        )
    )

    def fake_get_feed_detail(page_arg, feed_id, xsec_token, **kwargs):
        assert page_arg is page
        assert feed_id == "feed-1"
        assert xsec_token == "token-1"
        assert kwargs == {}
        return detail

    def fake_process_images(urls, save_dir=None):
        assert urls == ["https://img.example/a.jpg", "https://img.example/b.jpg"]
        assert save_dir == "/tmp/xhs_images"
        return ["/tmp/xhs_images/a.jpg", "/tmp/xhs_images/b.jpg"]

    def fake_ocr_images(paths, lang="chi_sim+eng", tesseract_cmd="tesseract"):
        assert paths == ["/tmp/xhs_images/a.jpg", "/tmp/xhs_images/b.jpg"]
        assert lang == "chi_sim+eng"
        assert tesseract_cmd == "tesseract"
        return [
            {"path": "/tmp/xhs_images/a.jpg", "text": "标题"},
            {"path": "/tmp/xhs_images/b.jpg", "text": "正文"},
        ]

    monkeypatch.setattr(cli, "_connect", lambda args: (browser, page))
    monkeypatch.setattr(xhs.feed_detail, "get_feed_detail", fake_get_feed_detail)
    monkeypatch.setattr(image_downloader, "process_images", fake_process_images)
    monkeypatch.setattr(image_ocr, "ocr_images", fake_ocr_images)
    monkeypatch.setattr(image_ocr, "parse_ocr_content", lambda texts: "\n".join(texts))
    monkeypatch.setattr(
        cli,
        "_output",
        lambda data, exit_code=0: captured.update(data=data, exit_code=exit_code),
    )

    parser = cli.build_parser()
    args = parser.parse_args(
        ["images-ocr", "--feed-id", "feed-1", "--xsec-token", "token-1"]
    )
    args.func(args)

    assert browser.closed is True
    assert captured == {
        "data": {
            "success": True,
            "feed_id": "feed-1",
            "output_dir": "/tmp/xhs_images",
            "count": 2,
            "images": [
                {"path": "/tmp/xhs_images/a.jpg", "text": "标题"},
                {"path": "/tmp/xhs_images/b.jpg", "text": "正文"},
            ],
            "content": "标题\n正文",
        },
        "exit_code": 0,
    }
