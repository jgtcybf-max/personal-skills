"""Read-only video inspection and single-pass contact sheets; no semantic approval.

Example:
  python review_media.py --video input.mp4 --out NEW_DIRECTORY --wait 45 \
      --focus 0:4:0.25 --focus 15.6:17.6:0.2
"""

from __future__ import annotations

import argparse
from bisect import bisect_left
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2
from PIL import Image, ImageDraw, ImageFont


def positive_number(value):
    try:
        result = float(Fraction(str(value)))
        return result if math.isfinite(result) and result > 0 else None
    except (ValueError, ZeroDivisionError, TypeError):
        return None


def focus_range(value):
    try:
        start, end, step = map(float, value.split(":"))
        if not all(math.isfinite(x) for x in (start, end, step)):
            raise ValueError
        if start < 0 or end < start or step <= 0:
            raise ValueError
        count = math.floor((end - start) / step + 1e-8) + 1
        if count > 1000:
            raise ValueError
        return {"start": start, "end": end, "step": step,
                "times": [round(start + i * step, 9) for i in range(count)]}
    except ValueError:
        raise argparse.ArgumentTypeError(
            "focus must be start:end:step, with 0 <= start <= end, step > 0, "
            "and at most 1000 samples"
        ) from None


def resolve_executable(explicit, name):
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError(f"{name} executable does not exist: {path}")
        return str(path)
    found = shutil.which(name)
    if found:
        return found
    if name == "ffprobe":
        ffmpeg = shutil.which("ffmpeg")
        candidates = ([Path(ffmpeg).with_name("ffprobe.exe")] if ffmpeg else [])
        candidates += [Path("C:/ffmpeg/bin/ffprobe.exe"),
                       Path("C:/Program Files/ffmpeg/bin/ffprobe.exe")]
        for path in candidates:
            if path.is_file():
                return str(path)
    return None


def probe_media(video, ffprobe, ffmpeg, timeout):
    """Return allowlisted fields only; never print raw metadata or stderr."""
    deadline = time.perf_counter() + timeout
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    if ffprobe:
        entries = ("format=duration:stream=index,codec_type,codec_name,width,height,"
                   "r_frame_rate,avg_frame_rate,duration,nb_frames,sample_rate,"
                   "channels,channel_layout")
        command = [ffprobe, "-v", "error", "-show_entries", entries,
                   "-of", "json", str(video)]
        try:
            result = subprocess.run(command, capture_output=True, timeout=timeout,
                                    creationflags=creationflags)
            raw = json.loads(result.stdout.decode("utf-8", errors="replace"))
            if result.returncode:
                raise ValueError
            # ffprobe can include stream tags/disposition despite show_entries.
            # Build fresh records rather than forwarding raw stream dictionaries.
            streams = []
            for stream in raw.get("streams", []):
                item = {"index": stream.get("index"),
                        "type": stream.get("codec_type"),
                        "codec": stream.get("codec_name")}
                if item["type"] == "video":
                    item.update({"width": stream.get("width"),
                                 "height": stream.get("height"),
                                 "fps": positive_number(stream.get("avg_frame_rate"))
                                        or positive_number(stream.get("r_frame_rate")),
                                 "duration_seconds": positive_number(stream.get("duration")),
                                 "declared_frames": positive_number(stream.get("nb_frames"))})
                elif item["type"] == "audio":
                    item.update({"sample_rate_hz": positive_number(stream.get("sample_rate")),
                                 "channels": stream.get("channels"),
                                 "channel_layout": stream.get("channel_layout"),
                                 "duration_seconds": positive_number(stream.get("duration"))})
                else:
                    continue
                streams.append(item)
            metadata = {"probe": "ffprobe", "streams": streams,
                        "container_duration_seconds": positive_number(
                            raw.get("format", {}).get("duration"))}
            if any(s["type"] == "video" for s in streams):
                return metadata
        except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
            pass
        # Fall back to FFmpeg when ffprobe exists but cannot inspect this input.
    if not ffmpeg:
        raise RuntimeError("No usable FFprobe/FFmpeg media probe is available")
    remaining = deadline - time.perf_counter()
    if remaining <= 0:
        raise RuntimeError("Media probe did not complete within the available time")
    try:
        result = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(video)],
                                capture_output=True, timeout=remaining,
                                creationflags=creationflags)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("FFmpeg media probe did not complete") from None
    details = result.stderr.decode("utf-8", errors="replace")
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", details)
    duration = (sum(float(x) * scale for x, scale in
                    zip(duration_match.groups(), (3600, 60, 1)))
                if duration_match else None)
    streams = []
    for line in details.splitlines():
        stream_match = re.match(r"\s*Stream #\d+:(\d+)(?:\[[^]]*\])?(?:\([^)]*\))?:\s*"
                                r"(Video|Audio):\s*([A-Za-z0-9_]+)", line)
        if not stream_match:
            continue
        index, kind, codec = stream_match.groups()
        item = {"index": int(index), "type": kind.lower(), "codec": codec}
        if kind == "Video":
            dimensions = re.search(r"(?<!\d)(\d{2,6})x(\d{2,6})(?!\d)", line)
            fps = re.search(r"([\d.]+)\s+fps\b", line)
            item.update({"width": int(dimensions[1]) if dimensions else None,
                         "height": int(dimensions[2]) if dimensions else None,
                         "fps": positive_number(fps[1]) if fps else None})
        else:
            sample_rate = re.search(r"(\d+)\s+Hz", line)
            layout = re.search(r"\d+\s+Hz,\s*([A-Za-z0-9. ()+-]+?)(?:,|$)", line)
            channel_layout = layout[1].strip() if layout else None
            channels = {"mono": 1, "stereo": 2, "2.1": 3,
                        "5.1": 6, "5.1(side)": 6, "7.1": 8}.get(channel_layout)
            item.update({"sample_rate_hz": int(sample_rate[1]) if sample_rate else None,
                         "channels": channels, "channel_layout": channel_layout})
        streams.append(item)
    if not any(s["type"] == "video" for s in streams):
        raise RuntimeError("FFmpeg could not read a video stream (raw diagnostic withheld)")
    return {"probe": "ffmpeg", "streams": streams,
            "container_duration_seconds": duration}


def ready_input(video, wait_seconds, ffprobe, ffmpeg):
    started = time.perf_counter()
    deadline = started + wait_seconds
    previous = None
    stable_since = None
    last_failure = "specified file is missing or empty"
    while True:
        now = time.perf_counter()
        try:
            stat = video.stat()
            if not video.is_file() or stat.st_size <= 0:
                raise OSError
            signature = (stat.st_size, stat.st_mtime_ns)
            if signature != previous:
                previous, stable_since = signature, now
            stable = not wait_seconds or now - stable_since >= 1.0
            if stable:
                remaining = deadline - time.perf_counter() if wait_seconds else 10
                if remaining <= 0:
                    break
                try:
                    metadata = probe_media(video, ffprobe, ffmpeg, min(10, remaining))
                    after = video.stat()
                    if (after.st_size, after.st_mtime_ns) == signature:
                        return metadata, signature, time.perf_counter() - started
                    last_failure = "specified file changed during metadata probing"
                except RuntimeError as error:
                    last_failure = str(error)
        except OSError:
            previous, stable_since = None, None
            last_failure = "specified file is missing, empty, or inaccessible"
        if not wait_seconds:
            raise RuntimeError(last_failure)
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            break
        time.sleep(min(0.25, remaining))
    raise RuntimeError(f"File readiness was not confirmed within {wait_seconds:g}s: {last_failure}")


def font_for(size):
    for filename in ("C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(filename, size)
        except OSError:
            pass
    return ImageFont.load_default()


def thumbnail(frame):
    picture = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    picture.thumbnail((236, 420), Image.Resampling.LANCZOS)
    return picture


def contact_sheet(records, output, columns=4):
    if not records:
        return False
    tile_width, tile_height = 240, max(r["image"].height for r in records) + 32
    rows = math.ceil(len(records) / columns)
    canvas = Image.new("RGB", (columns * tile_width, rows * tile_height), "white")
    draw = ImageDraw.Draw(canvas)
    font = font_for(15)
    for i, record in enumerate(records):
        x, y = i % columns * tile_width, i // columns * tile_height
        label = f'{record["seconds"]:.3f}s | frame {record["frame_index"]}'
        draw.text((x + 3, y + 3), label, font=font, fill="black")
        picture = record["image"]
        canvas.paste(picture, (x + (tile_width - picture.width) // 2, y + 29))
    canvas.save(output, quality=90)
    return True


def public_record(record):
    return {k: v for k, v in record.items() if k != "image"}


def inspect_video(video, output, focus_ranges):
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        cap.release()
        raise RuntimeError("OpenCV could not open the specified video")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = positive_number(cap.get(cv2.CAP_PROP_FPS))
    declared = positive_number(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    declared = int(declared) if declared else None
    if not fps or width <= 0 or height <= 0:
        cap.release()
        raise RuntimeError("Video dimensions or frame rate could not be determined")
    overview_indices = [round((declared - 1) * i / 23) for i in range(24)] if declared else []
    overview_targets = set(overview_indices)
    overview_records = {}
    # A bounded fallback sample bank handles absent/inaccurate declared frame counts.
    bank, bank_stride = {}, max(1, math.ceil(declared / 96)) if declared else 1
    focus_records = [[] for _ in focus_ranges]
    focus_positions = [0] * len(focus_ranges)
    first_records, last_frame, last_record = [], None, None
    decoded, last_seconds = 0, -1.0
    timestamp_fallback_frames = 0
    decode_started = time.perf_counter()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            seconds = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            if not math.isfinite(seconds) or seconds < 0 or (decoded and seconds <= last_seconds):
                seconds = decoded / fps
                timestamp_fallback_frames += 1
            seconds = max(seconds, last_seconds)
            last_seconds = seconds
            relevant_focus = []
            for n, interval in enumerate(focus_ranges):
                times, position = interval["times"], focus_positions[n]
                while position < len(times) and seconds + 1e-8 >= times[position]:
                    relevant_focus.append((n, times[position]))
                    position += 1
                focus_positions[n] = position
            need_bank = decoded % bank_stride == 0
            if decoded < 2 or decoded in overview_targets or relevant_focus or need_bank:
                record = {"frame_index": decoded, "seconds": round(seconds, 6),
                          "image": thumbnail(frame)}
                if decoded < 2:
                    first_records.append(record)
                    Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).save(
                        output / f"first_{decoded + 1:03d}.jpg", quality=92)
                if decoded in overview_targets:
                    overview_records[decoded] = record
                if need_bank:
                    bank[decoded] = record
                    if len(bank) > 192:
                        bank_stride *= 2
                        bank = {i: r for i, r in bank.items() if i % bank_stride == 0}
                for n, requested in relevant_focus:
                    focus_records[n].append({**record, "requested_seconds": requested})
            last_frame = frame
            decoded += 1
    finally:
        cap.release()
    if not decoded:
        raise RuntimeError("No video frames could be decoded")
    last_record = {"frame_index": decoded - 1, "seconds": round(last_seconds, 6),
                   "image": thumbnail(last_frame)}
    Image.fromarray(cv2.cvtColor(last_frame, cv2.COLOR_BGR2RGB)).save(
        output / "last.jpg", quality=92)
    decode_seconds = time.perf_counter() - decode_started
    sheet_started = time.perf_counter()
    if declared == decoded:
        overview = [overview_records[i] for i in overview_indices]
        overview_basis = "24 evenly spaced declared frame indices; declared count matched decode"
    else:
        bank[decoded - 1] = last_record
        indices = sorted(bank)
        overview = []
        for n in range(24):
            target = (decoded - 1) * n / 23
            position = bisect_left(indices, target)
            options = indices[max(0, position - 1):min(len(indices), position + 1)]
            selected = min(options, key=lambda i: abs(i - target))
            overview.append(bank[selected])
        overview_basis = "24 nearest samples from bounded sequential sample bank, including final frame"
    contact_sheet(overview, output / "overview_24.jpg")
    contact_sheet(first_records + [last_record], output / "first2_last.jpg", columns=3)
    focuses = []
    for n, (interval, records) in enumerate(zip(focus_ranges, focus_records), 1):
        filename = f"focus_{n:02d}_{interval['start']:g}-{interval['end']:g}s.jpg"
        produced = contact_sheet(records, output / filename)
        focuses.append({"start": interval["start"], "end": interval["end"],
                        "step": interval["step"], "requested_samples": len(interval["times"]),
                        "captured_samples": len(records), "file": filename if produced else None,
                        "samples": [public_record(r) for r in records]})
    return {"width": width, "height": height, "fps": fps,
            "declared_frames": declared, "decoded_frames": decoded,
            "duration_from_decoded_frames_seconds": decoded / fps,
            "last_frame_timestamp_seconds": last_seconds,
            "timestamp_fallback_frames": timestamp_fallback_frames,
            "all_declared_frames_decoded": decoded == declared if declared else None,
            "overview_sampling": overview_basis,
            "overview_samples": [public_record(r) for r in overview],
            "focus_sheets": focuses,
            "timings": {"sequential_decode_and_sample_seconds": decode_seconds,
                        "contact_sheet_save_seconds": time.perf_counter() - sheet_started}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, help="Exact media path; never modified")
    parser.add_argument("--out", required=True, help="New output directory; existing paths rejected")
    parser.add_argument("--wait", type=float, nargs="?", const=45, default=0,
                        help="Wait for stable size/mtime and readable metadata, at most 45 seconds")
    parser.add_argument("--focus", type=focus_range, action="append", default=[],
                        help="Repeatable start:end:step in seconds")
    parser.add_argument("--ffprobe", help="Optional FFprobe executable path")
    parser.add_argument("--ffmpeg", help="Optional FFmpeg executable path")
    args = parser.parse_args()
    if not math.isfinite(args.wait) or not 0 <= args.wait <= 45:
        parser.error("--wait must be between 0 and 45 seconds")
    if sum(len(f["times"]) for f in args.focus) > 2000:
        parser.error("at most 2000 total focus samples are supported")
    started = time.perf_counter()
    output = None
    created = False
    try:
        video = Path(args.video).expanduser().resolve()
        output = Path(args.out).expanduser().resolve()
        if output.exists() or output == video:
            raise RuntimeError("Output must be a new directory; existing paths are never overwritten")
        ffprobe = resolve_executable(args.ffprobe, "ffprobe")
        ffmpeg = resolve_executable(args.ffmpeg, "ffmpeg")
        probed, signature, readiness_seconds = ready_input(video, args.wait, ffprobe, ffmpeg)
        output.mkdir(parents=True, exist_ok=False)
        created = True
        decoded = inspect_video(video, output, args.focus)
        after = video.stat()
        unchanged = (after.st_size, after.st_mtime_ns) == signature
        metadata = {"input_file": str(video), "input_bytes": signature[0],
                    "input_unchanged_during_inspection": unchanged,
                    "probe": probed, **decoded,
                    "audio_streams": [s for s in probed["streams"] if s["type"] == "audio"],
                    "has_audio": any(s["type"] == "audio" for s in probed["streams"]),
                    "inspection_scope": "Technical video-frame decode and sampling only. "
                        "Audio presence is probed, not listened to or decoded. "
                        "No semantic, product consistency, motion-quality, or sound-content approval.",
                    "download_readiness_note": "--wait requires a one-second stable size/mtime "
                        "and readable metadata. A stalled download can still appear stable.",
                    "artifacts": sorted(p.name for p in output.iterdir()),
                    "wall_clock_seconds": time.perf_counter() - started}
        metadata["timings"]["readiness_and_probe_seconds"] = readiness_seconds
        metadata["artifacts"].append("metadata.json")
        (output / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(output), "decoded_frames": decoded["decoded_frames"],
                          "has_audio": metadata["has_audio"],
                          "all_declared_frames_decoded": decoded["all_declared_frames_decoded"],
                          "input_unchanged": unchanged,
                          "wall_clock_seconds": round(metadata["wall_clock_seconds"], 3)},
                         ensure_ascii=False))
        if not unchanged:
            return 2
        return 0 if decoded["all_declared_frames_decoded"] is not False else 2
    except (RuntimeError, OSError) as error:
        message = str(error)
        if created:
            (output / "error.json").write_text(
                json.dumps({"error": message, "wall_clock_seconds": time.perf_counter() - started},
                           ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Inspection failed: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
