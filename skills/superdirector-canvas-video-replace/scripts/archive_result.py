#!/usr/bin/env python3
"""Archive a downloaded edit beside its source video without overwriting files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid
from datetime import datetime, timedelta, timezone


def io_path(path: Path) -> str:
    value = str(path.absolute())
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        return "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
    return value


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(io_path(path), "rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def read_text(path: Path) -> str:
    with open(io_path(path), encoding="utf-8-sig") as handle:
        return handle.read()


def safe_name(value: str, limit: int | None = None) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    value = re.sub(r"\s+", " ", value) or "未命名"
    return value[:limit].rstrip(" .") if limit else value


def beijing_time(value: str | None) -> datetime:
    zone = timezone(timedelta(hours=8), "Asia/Shanghai")
    if not value:
        return datetime.now(zone)
    try:
        dt = datetime.strptime(value, "%Y%m%d-%H%M%S")
    except ValueError:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=zone) if dt.tzinfo is None else dt.astimezone(zone)


def require_file(value: str, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"{label}不是已存在的文件：{path}")
    return path


def write_exclusive(path: Path, text: str) -> None:
    with open(io_path(path), "x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def publish_no_replace(temporary: Path, output: Path) -> None:
    """Publish on the same volume atomically; never replace an existing path."""
    if os.name == "nt":
        # Windows rename fails when output already exists. POSIX rename does not.
        os.rename(io_path(temporary), io_path(output))
    else:
        os.link(io_path(temporary), io_path(output))
        os.unlink(io_path(temporary))


def copy_verified(result: Path, output: Path, expected_sha: str) -> None:
    """Keep incomplete copies out of the final filename and clean only our temp."""
    temporary = output.parent / (".sd-archive-" + uuid.uuid4().hex + ".partial")
    owned = False
    try:
        with open(io_path(result), "rb") as src, open(io_path(temporary), "xb") as dst:
            owned = True
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        shutil.copystat(io_path(result), io_path(temporary))
        if digest(temporary) != expected_sha:
            raise ValueError("归档临时副本哈希不一致，未发布正式文件。")
        publish_no_replace(temporary, output)
    finally:
        if owned and os.path.exists(io_path(temporary)):
            os.unlink(io_path(temporary))


def make_stem(source: Path, product: str, stage: str, setting: str, stamp: str) -> str:
    suffix = "__".join((safe_name(product, 40), safe_name(stage, 20), safe_name(setting, 30), stamp))
    # Leave space for sidecar suffixes and collisions. Long parent paths remain
    # supported on Windows through extended-length filesystem operations.
    name_budget = max(len(suffix) + 12, min(220, 242 - len(str(source.parent)) - 1))
    prefix_budget = max(1, name_budget - len(suffix) - 2)
    return safe_name(source.stem, prefix_budget) + "__" + suffix


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-video", required=True, help="原视频文件，归档至它所在的文件夹")
    p.add_argument("--result", required=True, help="已下载的生成视频文件")
    p.add_argument("--refs", required=True, help="本次商品参考图目录")
    p.add_argument("--prompt-file", required=True, help="UTF-8 提示词文本文件")
    p.add_argument("--review-file", help="UTF-8 人工或代理检查结果；缺省写明未检查")
    p.add_argument("--setting", required=True, help="实际选择的 UI 设置，例如 480原生 或 720标准")
    p.add_argument("--stage", default="测试01", help="例如 测试01、首版、正式01")
    p.add_argument("--product", required=True, help="商品货号/颜色，例如 987-黑色")
    p.add_argument("--model", help="实际使用的模型；未知时留空")
    p.add_argument("--timestamp", help="北京时间 YYYYMMDD-HHMMSS 或 ISO 时间，默认当前北京时间")
    return p


def archive(args: argparse.Namespace) -> dict:
    source = require_file(args.source_video, "原视频")
    result = require_file(args.result, "生成成片")
    if source == result:
        raise ValueError("生成成片与原视频不能是同一个文件。")
    prompt_path = require_file(args.prompt_file, "提示词")
    refs = Path(args.refs).expanduser().resolve()
    if not refs.is_dir():
        raise ValueError(f"商品图目录不存在：{refs}")
    review_path = require_file(args.review_file, "检查结果") if args.review_file else None
    prompt = read_text(prompt_path)
    review = read_text(review_path) if review_path else None
    timestamp = beijing_time(args.timestamp)
    result_sha = digest(result)
    source_sha = digest(source)
    ref_items = [
        {"name": item.name, "sha256": digest(item)}
        for item in sorted(refs.iterdir(), key=lambda path: path.name.casefold())
        if item.is_file() and item.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    ]
    if not ref_items:
        raise ValueError("商品图目录没有可识别的图片文件。")
    identity = {
        "source_video": str(source), "source_sha256": source_sha,
        "result_sha256": result_sha, "refs": str(refs), "reference_images": ref_items,
        "setting": args.setting, "stage": args.stage, "product": args.product,
        "model": args.model or None, "prompt": prompt, "review": review,
    }
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    for record_path in source.parent.glob("*__记录.json"):
        try:
            old = json.loads(read_text(record_path))
            if old.get("archive_fingerprint") != fingerprint:
                continue
            archived = Path(old["archive_video"])
            note = Path(old["archive_note"])
            if archived.is_file() and note.is_file() and digest(archived) == result_sha:
                return {"status": "already_archived", "video": str(archived), "note": str(note), "record": str(record_path), "sha256": result_sha}
        except (OSError, ValueError, KeyError, TypeError):
            continue

    stem = make_stem(source, args.product, args.stage, args.setting, timestamp.strftime("%Y%m%d-%H%M%S"))
    extension = result.suffix.lower() or ".mp4"
    for number in range(1, 10001):
        candidate_stem = stem + (f"__{number:02}" if number > 1 else "")
        output = source.parent / (candidate_stem + extension)
        note = source.parent / (candidate_stem + "__说明.md")
        record = source.parent / (candidate_stem + "__记录.json")
        if any(path.exists() for path in (output, note, record)):
            continue
        try:
            copy_verified(result, output, result_sha)
        except FileExistsError:
            continue
        break
    else:
        raise ValueError("无法找到未使用的归档文件名。")

    verified_sha = digest(output)
    if verified_sha != result_sha:
        raise ValueError(f"归档内容哈希不一致，请人工核对：{output}")
    model = args.model or "未知（未提供）"
    review_text = review or "未提供检查结果。本脚本只完成归档，尚未确认成片与商品图一致，不能标记为通过。"
    note_text = f"""# 视频元素替换归档说明

- 阶段：{args.stage}
- 商品：{args.product}
- 归档时间：{timestamp.isoformat(timespec='seconds')}（北京时间）
- 实际选择的 UI 设置：{args.setting}
- 模型：{model}
- 原视频：{source}
- 商品图目录：{refs}
- 生成下载原文件：{result}
- 同目录归档成片：{output}
- 成片 SHA-256：{result_sha}

## 参数和结论的证据范围

“{args.setting}”是操作时提供的 UI 设置，不等于实际像素尺寸、帧率或时长已经验证。本归档脚本不会重新生成、转码或修改视频，也不会自动判定商品一致性。实际媒体参数和质量结论以以下检查记录为准；未记录的项目仍属未知。

## 商品图目录文件清单

此清单是目录内图片，不代表它们全都已连接到生成节点，也不代表模型中的引用顺序；实际引用和编号以检查记录为准。

""" + "\n".join(f"- {item['name']}" for item in ref_items) + f"""

## 本次完整提示词

{prompt.rstrip()}

## 一致性检查及备注

{review_text.rstrip()}
"""
    write_exclusive(note, note_text)
    record_data = {
        "archive_fingerprint": fingerprint, "archived_at_beijing": timestamp.isoformat(timespec="seconds"),
        "archive_video": str(output), "archive_note": str(note),
        "downloaded_result": str(result), "prompt_file": str(prompt_path),
        "review_file": str(review_path) if review_path else None,
        **identity,
    }
    write_exclusive(record, json.dumps(record_data, ensure_ascii=False, indent=2) + "\n")
    return {"status": "archived", "video": str(output), "note": str(note), "record": str(record), "sha256": result_sha}


def main() -> int:
    try:
        result = archive(parser().parse_args())
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
