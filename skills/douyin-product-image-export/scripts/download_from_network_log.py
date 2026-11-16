#!/usr/bin/env python
import argparse
import json
import re
import time
import urllib.request
import zipfile
from pathlib import Path

try:
    from PIL import Image
except Exception:
    Image = None


def extract_urls(text: str):
    urls = []
    for match in re.finditer(r"https://[^\s\]]+", text):
        url = match.group(0).strip().rstrip(".,")
        if "ecom-shop-material" not in url:
            continue
        if not any(ext in url for ext in (".jpeg", ".jpg", ".png", ".webp", ".image")):
            continue
        if url not in urls:
            urls.append(url)
    return urls


def classify(urls, include_all=False):
    main = []
    detail = []
    other = []
    for url in urls:
        if "resize_q:1080:1080:q90.webp" in url:
            main.append(url)
        elif include_all or "resize:" in url or "tplv-5mmsx3fupr-xy" in url:
            detail.append(url)
        else:
            other.append(url)
    return main, detail, other


def ext_from_type(content_type: str, url: str):
    content_type = (content_type or "").lower()
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    if ".webp" in url:
        return ".webp"
    if ".png" in url:
        return ".png"
    return ".jpg"


def image_size(path: Path):
    if Image is None:
        return None
    try:
        with Image.open(path) as im:
            return list(im.size)
    except Exception:
        return None


def download(url: str, base_path: Path, retries=4):
    existing = sorted(base_path.parent.glob(f"{base_path.name}.*"))
    if existing:
        path = existing[0]
        return path, path.stat().st_size, "existing", image_size(path)

    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Referer": "https://haohuo.jinritemai.com/",
    }
    request = urllib.request.Request(url, headers=headers)
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read()
                content_type = response.headers.get("content-type", "")
            path = base_path.with_suffix(ext_from_type(content_type, url))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return path, len(data), content_type, image_size(path)
        except Exception as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise last_error


def zip_folder(folder: Path):
    zip_path = folder.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in folder.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(folder.parent))
    return zip_path


def main():
    parser = argparse.ArgumentParser(description="Download Douyin product main/detail images from a Playwright network log.")
    parser.add_argument("--network-log", required=True, help="Text file saved from browser_network_requests.")
    parser.add_argument("--output", required=True, help="Output folder.")
    parser.add_argument("--all-ecom-images", action="store_true", help="Download all ecom-shop-material images as detail images when not classified as main.")
    parser.add_argument("--detail-limit", type=int, default=0, help="Optional max number of detail images to download; 0 means all.")
    args = parser.parse_args()

    log_path = Path(args.network_log)
    output = Path(args.output)
    main_dir = output / "main_images"
    detail_dir = output / "detail_images"
    main_dir.mkdir(parents=True, exist_ok=True)
    detail_dir.mkdir(parents=True, exist_ok=True)

    urls = extract_urls(log_path.read_text(encoding="utf-8", errors="ignore"))
    main_urls, detail_urls, other_urls = classify(urls, args.all_ecom_images)
    if args.detail_limit > 0:
        detail_urls = detail_urls[: args.detail_limit]

    manifest = []
    errors = []

    for index, url in enumerate(main_urls, 1):
        try:
            path, byte_count, content_type, size = download(url, main_dir / f"main_{index:02d}")
            manifest.append({"type": "main", "index": index, "file": str(path), "url": url, "bytes": byte_count, "content_type": content_type, "size": size})
            print(f"downloaded main {index}: {path}")
        except Exception as exc:
            errors.append({"type": "main", "index": index, "url": url, "error": repr(exc)})
            print(f"ERROR main {index}: {exc}")

    for index, url in enumerate(detail_urls, 1):
        try:
            path, byte_count, content_type, size = download(url, detail_dir / f"detail_{index:02d}")
            manifest.append({"type": "detail", "index": index, "file": str(path), "url": url, "bytes": byte_count, "content_type": content_type, "size": size})
            print(f"downloaded detail {index}: {path}")
        except Exception as exc:
            errors.append({"type": "detail", "index": index, "url": url, "error": repr(exc)})
            print(f"ERROR detail {index}: {exc}")

    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
    zip_path = zip_folder(output)

    print(f"Saved folder: {output}")
    print(f"Saved zip: {zip_path}")
    print(f"Main images: {len([m for m in manifest if m['type'] == 'main'])}")
    print(f"Detail images: {len([m for m in manifest if m['type'] == 'detail'])}")
    print(f"Errors: {len(errors)}")


if __name__ == "__main__":
    main()
