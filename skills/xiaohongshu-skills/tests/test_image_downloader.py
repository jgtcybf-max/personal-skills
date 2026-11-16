"""Image downloader tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from image_downloader import ImageDownloader


class FakeResponse:
    status_code = 200
    content = b"image-bytes"


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, headers=None):
        self.calls.append((url, headers or {}))
        return FakeResponse()


def test_download_image_uses_xiaohongshu_referer_for_cdn_urls(tmp_path):
    downloader = ImageDownloader(str(tmp_path))
    fake_session = FakeSession()
    downloader._session = fake_session

    path = downloader.download_image(
        "https://sns-webpic-qc.xhscdn.com/path/to/image!nd_dft_wlteh_webp_3"
    )

    assert fake_session.calls[0][1]["Referer"] == "https://www.xiaohongshu.com/"
    assert path.endswith(".jpg")
