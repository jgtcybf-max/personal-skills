#!/usr/bin/env python3
"""Plan ordered frame replacement and verify downloaded PNGs without editing images."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
REFERENCE_ORDER = ("外侧面", "内侧面", "斜侧面", "后面", "正面", "鞋底", "内里")


def natural_key(value: str):
    """Stable number-aware ordering: 1, 2, 10; preserve original filenames."""
    return tuple(
        (0, int(part), len(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", value)
        if part
    )


def absolute(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def enumerate_images(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise ValueError(f"Image directory does not exist: {directory}")
    images = [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
    if not images:
        raise ValueError(f"No JPG/JPEG/PNG images found directly in: {directory}")
    return sorted(images, key=lambda p: (natural_key(p.name), p.name))


def reference_key(path: Path):
    # Only named views receive a preferred order. No shoe identity is inferred.
    try:
        rank = REFERENCE_ORDER.index(path.stem)
    except ValueError:
        rank = len(REFERENCE_ORDER)
    return rank, natural_key(path.name), path.name


def write_json(path: Path, value, *, exclusive: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def plan(args) -> dict:
    frame_dir, ref_dir, output, manifest = map(absolute, (args.frames, args.refs, args.output, args.manifest))
    if output in (frame_dir, ref_dir):
        raise ValueError("Output must be a separate folder from both input folders.")
    if manifest.exists():
        raise ValueError(f"Manifest already exists; resume it instead of replacing it: {manifest}")
    if any(is_within(manifest, folder) for folder in (frame_dir, ref_dir, output)):
        raise ValueError("Keep the manifest in a task work folder, outside inputs and final output.")
    frames = enumerate_images(frame_dir)
    references = sorted(enumerate_images(ref_dir), key=reference_key)
    output_names = [source.stem + ".png" for source in frames]
    if len({name.casefold() for name in output_names}) != len(output_names):
        raise ValueError("Duplicate frame stems would collide when saved as PNG; resolve the input names first.")
    if output.exists():
        if not output.is_dir():
            raise ValueError(f"Output path is not a directory: {output}")
        existing_images = [p for p in output.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
        if existing_images:
            raise ValueError(f"Output already contains image files; choose a new result folder: {output}")
    value = {
        "schemaVersion": 1,
        "runId": uuid.uuid4().hex[:12],
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "conversation": args.conversation or "",
        "framesDirectory": str(frame_dir),
        "referencesDirectory": str(ref_dir),
        "output": str(output),
        "refs": [str(p) for p in references],
        "frames": [
            {"index": index, "source": str(source), "outputName": name, "messageId": None, "saved": None}
            for index, (source, name) in enumerate(zip(frames, output_names), 1)
        ],
    }
    write_json(manifest, value, exclusive=True)
    return {
        "manifest": str(manifest),
        "frameCount": len(frames),
        "referenceCount": len(references),
        "output": str(output),
        "outputCreated": False,
        "firstFrame": output_names[0],
        "lastFrame": output_names[-1],
    }


def load_manifest(path: Path) -> tuple[dict, Path, list[dict]]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Manifest must be a JSON object.")
    output_value, frames = value.get("output"), value.get("frames")
    if not isinstance(output_value, str) or not output_value or not isinstance(frames, list) or not frames:
        raise ValueError("Manifest needs a nonempty output path and frames list.")
    output_path = Path(output_value).expanduser()
    if not output_path.is_absolute():
        raise ValueError("Manifest output must be an absolute path.")
    output = output_path.resolve()
    seen = set()
    for frame in frames:
        if not isinstance(frame, dict):
            raise ValueError("Each frames entry must be an object.")
        name = frame.get("outputName")
        if (
            not isinstance(name, str)
            or not name
            or "/" in name
            or "\\" in name
            or Path(name).name != name
            or Path(name).suffix.lower() != ".png"
        ):
            raise ValueError(f"Invalid PNG outputName: {name!r}")
        key = name.casefold()
        if key in seen:
            raise ValueError(f"Duplicate outputName in manifest: {name}")
        seen.add(key)
    return value, output, frames


def diagnostic_path(value: str | None, output: Path, manifest: Path) -> Path | None:
    if not value:
        return None
    result = absolute(value)
    if result == manifest or is_within(result, output):
        raise ValueError("Reports and contact sheets must be outside the final output and must not replace the manifest.")
    if result.exists():
        raise ValueError(f"Diagnostic output already exists; choose another path: {result}")
    return result


def make_contact_sheet(Image, ImageOps, ImageDraw, valid_rows: list[dict], target: Path):
    if not valid_rows:
        return False
    columns = min(5, len(valid_rows))
    cell_width, cell_height = 240, 370
    rows = (len(valid_rows) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(sheet)
    for i, row in enumerate(valid_rows):
        x, y = (i % columns) * cell_width, (i // columns) * cell_height
        with Image.open(row["output"]) as source:
            thumb = ImageOps.contain(source.convert("RGB"), (cell_width - 16, cell_height - 36))
            sheet.paste(thumb, (x + (cell_width - thumb.width) // 2, y + 30))
        label = row["outputName"]
        try:
            draw.text((x + 8, y + 8), label, fill="black")
        except UnicodeEncodeError:
            draw.text((x + 8, y + 8), str(row["index"]), fill="black")
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target)
    return True


def verify(args) -> tuple[dict, bool]:
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as error:
        raise ValueError("Verification requires Pillow; use a Python environment that already includes it or install Pillow.") from error
    manifest = absolute(args.manifest)
    value, output, frames = load_manifest(manifest)
    report_path = diagnostic_path(args.report, output, manifest)
    contact_path = diagnostic_path(args.contact_sheet, output, manifest)
    if report_path and report_path == contact_path:
        raise ValueError("Report and contact sheet must use different paths.")
    errors, results, by_hash = [], [], {}
    expected_names = {entry["outputName"].casefold() for entry in frames}
    if not output.is_dir():
        errors.append(f"Output directory does not exist: {output}")
        actual_images = []
    else:
        actual_images = [p for p in output.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
    extras = sorted([p.name for p in actual_images if p.name.casefold() not in expected_names], key=natural_key)
    if extras:
        errors.append("Unexpected image files: " + ", ".join(extras))
    if len(actual_images) != len(frames):
        errors.append(f"Expected {len(frames)} image files, found {len(actual_images)}.")
    for entry in frames:
        name = entry["outputName"]
        path = output / name
        row = {"index": entry.get("index"), "source": entry.get("source"), "outputName": name, "output": str(path), "ok": False}
        if not path.is_file():
            errors.append(f"Missing file: {name}")
            results.append(row)
            continue
        # Do not follow output symlinks outside the result directory.
        if not is_within(path.resolve(), output):
            errors.append(f"Output points outside the result directory: {name}")
            results.append(row)
            continue
        try:
            with Image.open(path) as image:
                width, height = image.size
                image_format = image.format
                image.verify()
            with Image.open(path) as image:
                image.load()
            if image_format != "PNG":
                raise ValueError(f"Content format is {image_format}, expected PNG")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            row.update(ok=True, width=width, height=height, bytes=path.stat().st_size, sha256=digest)
            by_hash.setdefault(digest, []).append(name)
        except (OSError, ValueError, SyntaxError) as error:
            errors.append(f"Unreadable or invalid PNG {name}: {error}")
        results.append(row)
    duplicates = [names for names in by_hash.values() if len(names) > 1]
    for names in duplicates:
        errors.append("Duplicate image content: " + ", ".join(names))
    dimensions = sorted({(r["width"], r["height"]) for r in results if r["ok"]})
    report = {
        "ok": not errors,
        "manifest": str(manifest),
        "output": str(output),
        "expectedCount": len(frames),
        "actualImageCount": len(actual_images),
        "readablePngCount": sum(row["ok"] for row in results),
        "uniqueImageCount": len(by_hash),
        "dimensions": [list(size) for size in dimensions],
        "duplicateGroups": duplicates,
        "extraImages": extras,
        "errors": errors,
        "results": results,
    }
    if contact_path:
        created = make_contact_sheet(Image, ImageOps, ImageDraw, [row for row in results if row["ok"]], contact_path)
        report["contactSheet"] = str(contact_path) if created else None
    if report_path:
        write_json(report_path, report, exclusive=True)
    return report, not errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan", help="Create an ordered manifest; no uploads, generation, or output images.")
    for name in ("frames", "refs", "output", "manifest"):
        planning.add_argument("--" + name, required=True)
    planning.add_argument("--conversation", default="")
    checking = commands.add_parser("verify", help="Read and verify downloaded result PNGs.")
    checking.add_argument("--manifest", required=True)
    checking.add_argument("--report")
    checking.add_argument("--contact-sheet")
    args = parser.parse_args()
    try:
        if args.command == "plan":
            print(json.dumps(plan(args), ensure_ascii=False, indent=2))
            return 0
        report, success = verify(args)
        # Keep ordinary stdout compact; the detailed report is optional.
        summary = {key: report[key] for key in ("ok", "expectedCount", "actualImageCount", "readablePngCount", "uniqueImageCount", "dimensions", "errors")}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if success else 1
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
