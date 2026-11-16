#!/usr/bin/env python
"""Export ordered, original-size Douyin product images from browser captures.

Requires Pillow. The browser capture, not network request arrival order, proves
the image set and its ordering. Downloaded image bytes are never re-encoded.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from PIL import Image, ImageDraw, ImageFont, ImageOps


HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://haohuo.jinritemai.com/"}
EXTENSIONS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp", "GIF": ".gif", "AVIF": ".avif"}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resource_id(url):
    """Remove CDN host, rendition and query while retaining the resource key."""
    value = str(url or "").strip()
    if value.startswith(("http://", "https://", "//")):
        value = urllib.parse.unquote(urllib.parse.urlsplit(value).path)
    value = value.split("~", 1)[0].split("?", 1)[0].lstrip("/")
    if value.startswith("img/"):
        value = value[4:]
    return value


def image_url(item):
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        raise ValueError("Image entry must be a URL string or an object")
    for key in ("url", "src", "currentSrc"):
        if item.get(key):
            return item[key]
    urls = item.get("url_list", [])
    if urls:
        return urls[0]
    if isinstance(item.get("image"), dict):
        return image_url(item["image"])
    raise ValueError("Image entry is missing a usable URL")


def entry_object(item):
    if isinstance(item, str):
        return {"url": item}
    if isinstance(item, dict) and isinstance(item.get("image"), dict):
        return item["image"]
    return item


def dimensions(item):
    item = entry_object(item)
    if not isinstance(item, dict):
        return None
    width = item.get("width", item.get("naturalWidth", 0))
    height = item.get("height", item.get("naturalHeight", 0))
    try:
        result = [int(width or 0), int(height or 0)]
    except (TypeError, ValueError):
        return None
    return result if min(result) > 0 else None


def declared_size(uri):
    match = re.search(r"_www(\d+)-(\d+)(?:$|[._])", uri)
    return [int(match[1]), int(match[2])] if match else None


def api_container(data, name):
    if name in data:
        return data[name]
    if isinstance(data.get("data"), dict) and name in data["data"]:
        return data["data"][name]
    raise ValueError(f"API capture does not contain {name}; refresh it or use DOM-only capture")


def unique_path(path):
    path = Path(path)
    if not path.exists():
        return path
    number = 2
    while True:
        candidate = path.with_name(f"{path.stem}_v{number}{path.suffix}")
        if not candidate.exists():
            return candidate
        number += 1


def reserve_output(requested):
    requested = Path(requested).expanduser().resolve()
    # Never mix products/runs, overwrite delivered files, or trust stale images.
    if requested.exists() and (not requested.is_dir() or any(requested.iterdir())):
        number = 2
        while True:
            candidate = requested.with_name(f"{requested.name}_v{number}")
            if not candidate.exists():
                requested = candidate
                break
            number += 1
    requested.mkdir(parents=True, exist_ok=True)
    for name in ("main_images", "detail_images"):
        (requested / name).mkdir(exist_ok=True)
    return requested


def check_order(api, dom, label):
    first = [resource_id(image_url(item)) for item in api]
    second = [resource_id(image_url(item)) for item in dom]
    if first != second:
        raise ValueError(f"{label} API/DOM image order differs ({len(first)} API, {len(second)} DOM); refresh capture")


def capture_sources(args):
    dom = load_json(args.dom_images)
    if not isinstance(dom, dict):
        raise ValueError("DOM capture must be a JSON object")
    if not isinstance(dom.get("carousel"), list) or not dom["carousel"]:
        raise ValueError("DOM capture needs a nonempty ordered carousel array")
    if not isinstance(dom.get("details"), list):
        raise ValueError("DOM capture needs an ordered details array, even when empty")
    if dom.get("atBottom") is not True:
        raise ValueError("DOM capture does not prove the product details were scrolled to the bottom")
    for key in ("allImagesLoaded", "detailsExpanded"):
        if key in dom and dom[key] is not True:
            raise ValueError(f"DOM capture reports {key}=false; finish loading/expanding first")
    for position, item in enumerate(dom["details"], 1):
        if dimensions(item) is None or (isinstance(item, dict) and
                                        (item.get("complete") is False or item.get("loaded") is False)):
            raise ValueError(f"DOM detail position {position} is not fully loaded (natural dimensions missing)")
    for position, item in enumerate(dom["carousel"], 1):
        if isinstance(item, dict) and (item.get("complete") is False or item.get("loaded") is False):
            raise ValueError(f"DOM carousel position {position} is not fully loaded")

    h5 = api_container(load_json(args.h5_response), "promotion_h5") if args.h5_response else None
    detail = api_container(load_json(args.detail_response), "detail_info") if args.detail_response else None
    dom_id = str(dom.get("productId") or dom.get("product_id") or "").strip()
    if not dom_id:
        raise ValueError("DOM capture must identify the actual productId")
    if h5 is not None:
        info = h5.get("basic_info_data", {})
        api_id = str(info.get("product_id") or "").strip()
        if api_id != dom_id:
            raise ValueError(f"Product ID mismatch between API ({api_id}) and DOM ({dom_id})")
        title = str(info.get("title_info", {}).get("title") or "").strip()
        mains = []
        for media in h5.get("head_figure_data", {}).get("media_list", []):
            if media.get("type") == "image":
                mains.extend(media.get("content_list", []))
        if not mains:
            raise ValueError("H5 API does not contain an ordered image carousel")
        check_order(mains, dom["carousel"], "Main")
    else:
        title = str(dom.get("title") or dom.get("productName") or args.product_name or "").strip()
        mains = dom["carousel"]
    if not title:
        raise ValueError("A verified product title is required in the H5 API, DOM capture, or --product-name")
    dom_title = str(dom.get("title") or dom.get("productName") or "").strip()
    if dom_title and dom_title != title:
        raise ValueError("Product title differs between API and DOM")
    if args.product_name and args.product_name.strip() != title:
        raise ValueError("--product-name differs from the captured product title")
    if args.product_id and str(args.product_id).strip() != dom_id:
        raise ValueError("--product-id differs from the captured product ID")

    if detail is not None:
        if isinstance(detail.get("detail_imgs_new"), list):
            details = [entry_object(item) for item in detail["detail_imgs_new"]]
            if isinstance(detail.get("detail_imgs"), list):
                check_order(details, detail["detail_imgs"], "Detail API variants")
        elif isinstance(detail.get("detail_imgs"), list):
            details = detail["detail_imgs"]
        else:
            raise ValueError("Detail API is missing both detail_imgs_new and detail_imgs arrays")
        check_order(details, dom["details"], "Detail")
    else:
        details = dom["details"]

    tasks, duplicates = [], []
    for kind, records, is_api in (("main", mains, h5 is not None), ("detail", details, detail is not None)):
        seen = {}
        for position, raw in enumerate(records, 1):
            item = entry_object(raw)
            url = image_url(item)
            uri = resource_id(item.get("uri") or url)
            if not uri:
                raise ValueError(f"Empty resource identity for {kind} position {position}")
            if uri in seen:
                duplicates.append({"kind": kind, "page_position": position,
                                   "same_as_page_position": seen[uri]["page_position"],
                                   "saved_index": seen[uri]["index"], "uri": uri})
                continue
            expected = declared_size(uri)
            api_size = dimensions(item) if is_api else None
            if expected and api_size and expected != api_size:
                raise ValueError(f"Conflicting original dimensions for {kind} position {position}")
            expected = expected or api_size
            explicit = item.get("original_url") or item.get("originalUrl")
            if explicit is None and item.get("original") is True:
                explicit = url
            if explicit is None and re.search(r"~tplv-[^/?]+-(?:image\.png|origin[-.][^/?]+|ec-imagex-origin\.[^/?]+)$", url):
                explicit = url
            record = {"kind": kind, "index": len(seen) + 1, "page_position": position,
                      "uri": uri, "expected_size": expected, "page_image_url": url,
                      "original_url": explicit, "source": "api" if is_api else "dom"}
            tasks.append(record)
            seen[uri] = record
    return {"title": title, "product_id": dom_id, "page_counts": {"main": len(mains), "detail": len(details)},
            "source_mode": "api_and_dom" if h5 is not None and detail is not None else "dom_or_mixed",
            "at_bottom": True, "details_loaded": True, "duplicate_page_entries": duplicates}, tasks


def original_candidates(task):
    candidates = []
    if task.get("original_url"):
        candidates.append(task["original_url"])
    url_host = urllib.parse.urlsplit(task["page_image_url"]).hostname or ""
    known_resource = task["uri"].startswith(("ecom-shop-material/", "tos-cn-i-5mmsx3fupr/"))
    if task["expected_size"] and (url_host.endswith(".ecombdimg.com") or known_resource):
        for host in ("p26-item.ecombdimg.com", "p3-item.ecombdimg.com"):
            prefix = "img/" if task["uri"].startswith("ecom-shop-material/") else ""
            candidates.append(f'https://{host}/{prefix}{task["uri"]}~tplv-5mmsx3fupr-image.png')
    # Unknown-size entries need an explicit original; page thumbnails are not a fallback.
    return list(dict.fromkeys(candidates))


def download(task, root, timeout):
    attempts = []
    candidates = original_candidates(task)
    if not candidates:
        return dict(task, errors=[{"error": "No explicit original URL or verifiable original-size endpoint"}])
    for url in candidates:
        if not url.startswith(("https://", "http://")):
            attempts.append({"url": url, "error": "Original URL must use HTTP or HTTPS"})
            continue
        # One short retry for a transient transport/server failure, then try another CDN.
        for attempt in range(2):
            try:
                request = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    payload = response.read()
                    content_type = response.headers.get("Content-Type", "")
                with Image.open(io.BytesIO(payload)) as image:
                    image.load()
                    size, fmt = list(image.size), image.format
                if task["expected_size"] and size != task["expected_size"]:
                    raise ValueError(f'Original dimensions differ: {size}, expected {task["expected_size"]}')
                if fmt not in EXTENSIONS:
                    raise ValueError(f"Unsupported actual image format: {fmt}")
                path = root / f'{task["kind"]}_images' / f'{task["kind"]}_{task["index"]:02d}{EXTENSIONS[fmt]}'
                with path.open("xb") as output:
                    output.write(payload)
                result = dict(task, file=str(path), relative_file=path.relative_to(root).as_posix(),
                              original_size_url=url, actual_size=size, format=fmt,
                              content_type=content_type, bytes=len(payload),
                              sha256=hashlib.sha256(payload).hexdigest(), attempts=attempts,
                              original_resolution_verified=bool(task["expected_size"]),
                              original_integrity="verified_dimensions" if task["expected_size"] else "unverified_dimensions")
                print(f'OK {task["kind"]}_{task["index"]:02d} {size[0]}x{size[1]} {fmt}', flush=True)
                return result
            except Exception as error:
                attempts.append({"url": url, "attempt": attempt + 1, "error": str(error)})
                if isinstance(error, (ValueError, FileExistsError)):
                    break
                if isinstance(error, urllib.error.HTTPError) and error.code < 500:
                    break
    print(f'FAILED {task["kind"]}_{task["index"]:02d}', flush=True)
    return dict(task, errors=attempts)


def font(size):
    for name in ("C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def make_preview(rows, root):
    if not rows:
        return None
    columns, cell_w, cell_h = min(5, len(rows)), 320, 365
    count_rows = (len(rows) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_w, count_rows * cell_h), "#eeeeee")
    draw = ImageDraw.Draw(sheet)
    label_font = font(18)
    for i, row in enumerate(rows):
        x, y = i % columns * cell_w, i // columns * cell_h
        with Image.open(row["file"]) as image:
            thumb = ImageOps.contain(image.convert("RGB"), (296, 296))
        draw.rectangle((x + 12, y + 12, x + 307, y + 307), fill="white")
        sheet.paste(thumb, (x + (cell_w - thumb.width) // 2, y + 12 + (296 - thumb.height) // 2))
        label = f'main_{row["index"]:02d}  {row["actual_size"][0]} x {row["actual_size"][1]}'
        draw.text((x + 12, y + 323), label, font=label_font, fill="#222222")
    target = root / "主图预览联系表.png"
    sheet.save(target, "PNG")
    return target


def write_sources(manifest, root):
    counts = manifest["saved_counts"]
    lines = [f'商品名称：{manifest["title"]}', f'商品分享链接：{manifest["share_link"]}',
             f'实际商品ID：{manifest["product_id"]}', f'下载时间：{manifest["captured_at"]}', "",
             f'页面轮播位置：{manifest["page_counts"]["main"]}；成功保存主图：{counts["main"]}张。',
             f'页面详情位置：{manifest["page_counts"]["detail"]}；成功保存详情图：{counts["detail"]}张。',
             f'最终下载失败或无法读取：{manifest["failure_count"]}张。',
             f'原分辨率已核对：{manifest["verified_original_count"]}张；原尺寸无法独立核对：{manifest["unverified_original_count"]}张。', "",
             '范围核对：已读取商品页有序图片列表并滚动详情区域至底部；已载入所有详情图片。',
             f'来源模式：{manifest["source_mode"]}。API存在时已与商品DOM逐项核对顺序和商品ID。',
             '去重按同一类别的资源ID保留首次出现；CDN域名或缩略版本不另计一张。',
             '图片直接保存HTTP响应文件；未本地缩放、裁切、重绘或重新压缩。',
             'CDN原分辨率版本不等于取得商家最初上传文件的原始压缩字节；格式按实际解码保存。', "", '重复图片记录：']
    duplicates = manifest["duplicate_page_entries"]
    if not duplicates:
        lines.append('无。')
    for item in duplicates:
        lines.append(f'{item["kind"]} 页面第{item["page_position"]}项与第{item["same_as_page_position"]}项为同一资源；保留为{item["kind"]}_{item["saved_index"]:02d}。')
    lines += ["", "下载失败或无法读取清单："]
    failures = [row for row in manifest["images"] if "errors" in row]
    if not failures:
        lines.append("无。")
    for item in failures:
        lines += [f'{item["kind"]}_{item["index"]:02d}（页面第{item["page_position"]}项）',
                  f'页面地址：{item["page_image_url"]}', json.dumps(item["errors"], ensure_ascii=False)]
    lines += ["", "逐图来源（按类别及页面顺序）："]
    for item in manifest["images"]:
        if "file" not in item:
            continue
        verification = "尺寸已核对" if item["original_resolution_verified"] else "原尺寸未独立核对"
        lines += ["", item["relative_file"],
                  f'页面第{item["page_position"]}项；{item["actual_size"][0]}×{item["actual_size"][1]}；{item["format"]}；{item["bytes"]}字节；{verification}',
                  f'页面图片地址：{item["page_image_url"]}', f'下载地址：{item["original_size_url"]}',
                  f'SHA256：{item["sha256"]}']
    path = root / "来源清单.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path


def package(root, archive):
    files = sorted(path for path in root.rglob("*") if path.is_file())
    expected = {path.relative_to(root.parent).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in files}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for file in files:
            bundle.write(file, file.relative_to(root.parent).as_posix())
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None or set(bundle.namelist()) != set(expected):
            raise ValueError("ZIP CRC/member verification failed")
        for name, digest in expected.items():
            if hashlib.sha256(bundle.read(name)).hexdigest() != digest:
                raise ValueError(f"ZIP hash differs: {name}")
    return len(files)


def run(args):
    metadata, tasks = capture_sources(args)
    root = reserve_output(args.output)
    archive = unique_path(Path(args.zip_output).expanduser().resolve() if args.zip_output else root.with_name(root.name + ".zip"))
    if archive == root or root in archive.parents:
        raise ValueError("ZIP output must be outside the image export folder")
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(download, task, root, args.timeout) for task in tasks]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: (0 if item["kind"] == "main" else 1, item["index"]))
    saved = [item for item in results if "file" in item]
    errors = [item for item in results if "errors" in item]
    mains = [item for item in saved if item["kind"] == "main"]
    details = [item for item in saved if item["kind"] == "detail"]
    preview = make_preview(mains, root)
    verified = sum(item["original_resolution_verified"] for item in saved)
    manifest = dict(metadata, share_link=args.share_url, captured_at=datetime.now().astimezone().isoformat(),
                    output=str(root), archive=str(archive), archive_verification="see_sibling_verification_result",
                    saved_counts={"main": len(mains), "detail": len(details)},
                    unique_requested_counts={kind: sum(item["kind"] == kind for item in tasks) for kind in ("main", "detail")},
                    failure_count=len(errors), verified_original_count=verified,
                    unverified_original_count=len(saved) - verified,
                    original_resolution_all_verified=not errors and len(saved) == verified,
                    file_bytes_preserved=True, preview=str(preview) if preview else None, images=results)
    source_file = write_sources(manifest, root)
    manifest["source_list"] = str(source_file)
    save_json(root / "manifest.json", manifest)
    save_json(root / "errors.json", errors)
    # Keep the final verification result beside the archive and print it so that
    # the packaged manifest and the output-directory manifest remain identical.
    file_count = package(root, archive)
    verification = {"output": str(root), "archive": str(archive), "archive_verified": True,
                    "archive_files": file_count, "counts": manifest["saved_counts"],
                    "failure_count": len(errors), "verified_original_count": verified,
                    "unverified_original_count": len(saved) - verified,
                    "preview": str(preview) if preview else None, "source_list": str(source_file)}
    result_path = unique_path(archive.with_name(archive.stem + "_验证结果.json"))
    save_json(result_path, verification)
    print(json.dumps(verification, ensure_ascii=True), flush=True)
    return 1 if errors else 0


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--h5-response", help="Saved promotion/pack/h5 JSON response (optional).")
    result.add_argument("--detail-response", help="Saved promotion/pack/detail JSON response (optional).")
    result.add_argument("--dom-images", required=True, help="Ordered product DOM image capture JSON with productId and atBottom.")
    result.add_argument("--share-url", required=True, help="Original user-provided product share URL.")
    result.add_argument("--output", required=True, help="Requested output folder; a nonempty folder is versioned automatically.")
    result.add_argument("--product-name", help="Validate the captured title, or supply it for DOM-only capture.")
    result.add_argument("--product-id", help="Validate the captured actual product ID.")
    result.add_argument("--zip-output", help="Requested ZIP path, outside the output folder; existing ZIPs are versioned.")
    result.add_argument("--workers", type=int, default=6, help="Concurrent downloads (default: 6).")
    result.add_argument("--timeout", type=float, default=18, help="HTTP timeout in seconds per attempt (default: 18).")
    return result


def main():
    args = parser().parse_args()
    if args.workers < 1 or args.workers > 16 or args.timeout <= 0 or args.timeout > 60:
        parser().error("Use 1-16 workers and a timeout greater than 0 and no more than 60 seconds")
    try:
        return run(args)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
