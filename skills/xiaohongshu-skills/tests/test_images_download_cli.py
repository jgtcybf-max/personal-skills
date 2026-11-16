"""images-download CLI tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cli
import image_downloader
import xhs.feed_detail


class DummyBrowser:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_images_download_fetches_detail_images_and_saves_to_default_dir(monkeypatch):
    browser = DummyBrowser()
    page = object()
    captured: dict = {}

    detail = SimpleNamespace(
        note=SimpleNamespace(
            image_list=[
                SimpleNamespace(url_default="https://img.example/a.jpg", url_pre=""),
                SimpleNamespace(url_default="", url_pre="https://img.example/b.webp"),
                SimpleNamespace(url_default="", url_pre=""),
            ]
        )
    )

    def fake_get_feed_detail(page_arg, feed_id, xsec_token, **kwargs):
        assert page_arg is page
        assert feed_id == "69ad4bb9000000000d00a454"
        assert xsec_token == "token-value"
        assert kwargs == {}
        return detail

    def fake_process_images(urls, save_dir=None):
        assert urls == ["https://img.example/a.jpg", "https://img.example/b.webp"]
        assert save_dir == "/tmp/xhs_images"
        return ["/tmp/xhs_images/a.jpg", "/tmp/xhs_images/b.webp"]

    monkeypatch.setattr(cli, "_connect", lambda args: (browser, page))
    monkeypatch.setattr(xhs.feed_detail, "get_feed_detail", fake_get_feed_detail)
    monkeypatch.setattr(image_downloader, "process_images", fake_process_images)
    monkeypatch.setattr(
        cli,
        "_output",
        lambda data, exit_code=0: captured.update(data=data, exit_code=exit_code),
    )

    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "images-download",
            "--feed-id",
            "69ad4bb9000000000d00a454",
            "--xsec-token",
            "token-value",
        ]
    )
    args.func(args)

    assert browser.closed is True
    assert captured == {
        "data": {
            "success": True,
            "feed_id": "69ad4bb9000000000d00a454",
            "output_dir": "/tmp/xhs_images",
            "count": 2,
            "paths": ["/tmp/xhs_images/a.jpg", "/tmp/xhs_images/b.webp"],
        },
        "exit_code": 0,
    }
