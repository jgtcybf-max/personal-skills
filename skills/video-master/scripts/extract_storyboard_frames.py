#!/usr/bin/env python3
"""Extract clean and labelled storyboard frames from a source video."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Local adaptation 2026-11-16; original project AI 创意研究室, AGPL-3.0-only.
from media_runtime import configure_media_path


def extract(video: Path, timestamp: float, destination: Path) -> float:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{timestamp:.6f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", "-y", str(destination)]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Failed to extract {timestamp}")
    actual_timestamp = timestamp
    if not destination.is_file():
        # Local fix 2026-11-16: an EOF seek can succeed while emitting no frame.
        from inspect_video import probe
        media = probe(video)
        safe_last = max(0.0, media["duration"] - 1.0 / (media["fps"] or 25.0))
        if timestamp > safe_last:
            actual_timestamp = safe_last
            cmd[cmd.index("-ss") + 1] = f"{safe_last:.6f}"
            retry = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if retry.returncode:
                raise RuntimeError(retry.stderr.strip() or "Last-frame extraction failed")
            print(f"End-frame timestamp adjusted: {timestamp:.6f}s -> {safe_last:.6f}s", file=sys.stderr)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"No frame was emitted for {timestamp:.6f}s")
    return actual_timestamp


def annotate(source: Path, destination: Path, label: str) -> None:
    image = Image.open(source).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    font = ImageFont.load_default(size=max(14, image.width // 70))
    bbox = draw.textbbox((0, 0), label, font=font)
    padding = max(8, image.width // 120)
    height = bbox[3] - bbox[1] + padding * 2
    draw.rectangle((0, 0, image.width, height), fill=(8, 15, 28, 210))
    draw.text((padding, padding), label, fill=(255, 255, 255, 255), font=font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG")


def labels(count: int) -> list[str]:
    return [f"node-{i:02d}" for i in range(1, count + 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    configure_media_path()
    if shutil.which("ffmpeg") is None:
        raise SystemExit("Required executable not found: ffmpeg")
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    clean_dir = args.output_dir / "clean"
    annotated_dir = args.output_dir / "annotated"
    frame_index = []
    for segment in data.get("segments", []):
        times = [float(x) for x in segment.get("keyframe_times", [])]
        impact_roles: dict[float, list[str]] = {}
        for shot in segment.get("shot_prompts", []):
            for event in shot.get("impact_events", []):
                center = float(event["source_time"])
                for timestamp in event.get("dense_keyframe_times", []):
                    value = float(timestamp)
                    phase = "impact"
                    if value < center - 0.015:
                        phase = "pre-impact"
                    elif value > center + 0.015:
                        phase = "post-impact"
                    impact_roles.setdefault(round(value, 6), []).append(f"{event['event_id']}:{phase}")
        names = labels(len(times))
        for name, timestamp in zip(names, times):
            filename = f"{segment['segment_id']}-{name}.png"
            clean = clean_dir / filename
            labelled = annotated_dir / filename
            actual_timestamp = extract(args.video, timestamp, clean)
            evidence_roles = impact_roles.get(round(timestamp, 6), [])
            suffix = f" | {', '.join(evidence_roles)}" if evidence_roles else ""
            annotate(clean, labelled, f"{segment['segment_id']} | {actual_timestamp:.2f}s | {name}{suffix}")
            frame_index.append({"segment_id": segment["segment_id"], "timestamp": timestamp, "extracted_timestamp": actual_timestamp, "role": name, "evidence_roles": evidence_roles, "clean": str(clean), "annotated": str(labelled)})
    index_path = args.output_dir / "frame-index.json"
    index_path.write_text(json.dumps(frame_index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Extracted {len(frame_index)} frames to {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
