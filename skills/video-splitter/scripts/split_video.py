"""Split a local video into accurate, numbered segments using FFmpeg."""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def ffmpeg_path() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    if importlib.util.find_spec("imageio_ffmpeg"):
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    raise RuntimeError("FFmpeg not found. Install FFmpeg or run: python -m pip install imageio-ffmpeg")


def duration_seconds(ffmpeg: str, source: Path) -> float:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(source)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stdout)
    if not match:
        raise RuntimeError(f"Could not read video duration from {source}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--prefix", default="视频素材")
    parser.add_argument("--extension", help="Output extension, including the dot; defaults to input extension")
    args = parser.parse_args()

    source = args.input.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Input file does not exist: {source}")
    if args.count < 1:
        raise SystemExit("--count must be at least 1")

    output_dir = (args.output_dir or source.parent).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    extension = args.extension or source.suffix or ".mp4"
    if not extension.startswith("."):
        extension = "." + extension

    ffmpeg = ffmpeg_path()
    total = duration_seconds(ffmpeg, source)
    segment = total / args.count

    for index in range(args.count):
        start = index * segment
        length = total - start if index == args.count - 1 else segment
        target = output_dir / f"{args.prefix}{index + 1}{extension}"
        command = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.6f}",
            "-i",
            str(source),
            "-t",
            f"{length:.6f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(target),
        ]
        subprocess.run(command, check=True)
        print(f"{target}\t{length:.3f}s")

    print(f"Created {args.count} clips from {source} ({total:.3f}s total)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode or 1)
