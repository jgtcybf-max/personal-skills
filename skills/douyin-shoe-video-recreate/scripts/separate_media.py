"""Export a stream-copied silent MP4 and original audio; optionally add MP3."""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def find_ffmpeg():
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError("FFmpeg is missing; install ffmpeg or imageio-ffmpeg.") from exc


def run(ffmpeg, args, check=True):
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostdin", *map(str, args)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr[-3500:])
    return result


def probe(ffmpeg, path):
    result = run(ffmpeg, ["-i", path], check=False)
    duration = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    streams = []
    for line in result.stderr.splitlines():
        match = re.search(r"Stream #\d+:\d+.*?: (Video|Audio): ([\w]+)", line)
        if match:
            streams.append({"type": match[1].lower(), "codec": match[2]})
    if not duration or not streams:
        raise RuntimeError(f"Cannot probe media: {path}\n{result.stderr[-1500:]}")
    hours, minutes, seconds = map(float, duration.groups())
    video_size = re.search(r"Video:.*?\b(\d{2,6})x(\d{2,6})\b", result.stderr)
    fps = re.search(r"Video:.*?([\d.]+) fps", result.stderr)
    return {
        "duration": hours * 3600 + minutes * 60 + seconds,
        "streams": streams,
        "width": int(video_size[1]) if video_size else None,
        "height": int(video_size[2]) if video_size else None,
        "fps": float(fps[1]) if fps else None,
    }


def packet_hash(ffmpeg, path, stream):
    result = run(ffmpeg, ["-v", "error", "-i", path, "-map", stream,
                          "-c", "copy", "-f", "hash", "-hash", "sha256", "-"])
    value = result.stdout.strip()
    if not value.startswith("SHA256="):
        raise RuntimeError(f"Missing packet hash for {path}")
    return value


def validate(ffmpeg, path, media_type, source):
    metadata = probe(ffmpeg, path)
    if [s["type"] for s in metadata["streams"]] != [media_type]:
        raise RuntimeError(f"Unexpected streams in {path}: {metadata['streams']}")
    if abs(metadata["duration"] - source["duration"]) > 0.2:
        raise RuntimeError(f"Duration mismatch in {path}")
    if media_type == "video":
        for key in ("width", "height", "fps"):
            if metadata[key] != source[key]:
                raise RuntimeError(f"Video {key} changed in {path}")
    stream = "0:v:0" if media_type == "video" else "0:a:0"
    result = run(ffmpeg, ["-v", "error", "-xerror", "-i", path,
                          "-map", stream, "-f", "null", "-"])
    if result.stderr.strip():
        raise RuntimeError(f"Decode errors in {path}: {result.stderr[-1500:]}")
    return metadata


def publish_exclusive(source, destination):
    # Exclusive creation prevents overwriting even if another run races this one.
    created = False
    try:
        with destination.open("xb") as output:
            created = True
            with source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output)
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--prefix")
    parser.add_argument("--mp3", action="store_true", help="Also encode an MP3 copy.")
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    output_dir = (args.output_dir or source.parent).resolve()
    prefix = args.prefix or source.stem
    if not prefix.strip() or re.search(r'[<>:"/\\|?*\x00-\x1f]', prefix) or prefix.endswith((" ", ".")):
        parser.error("Prefix must be a valid filename stem, not a path.")
    ffmpeg = find_ffmpeg()
    metadata = probe(ffmpeg, source)
    audio_streams = [s for s in metadata["streams"] if s["type"] == "audio"]
    if not any(s["type"] == "video" for s in metadata["streams"]):
        parser.error("Source has no video stream.")
    if not audio_streams:
        parser.error("Source has no audio track; no original audio can be extracted.")
    audio_codec = audio_streams[0]["codec"]
    extension = {"aac": ".m4a", "alac": ".m4a", "mp3": ".mp3", "opus": ".ogg",
                 "vorbis": ".ogg", "flac": ".flac"}.get(audio_codec, ".mka")
    names = {"silent_video": prefix + "_静音.mp4", "original_audio": prefix + "_原音频" + extension}
    if args.mp3:
        names["mp3_audio"] = prefix + "_音频_转码.mp3"
    destinations = {key: output_dir / name for key, name in names.items()}
    for path in destinations.values():
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite: {path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {"source": str(source), "source_metadata": metadata, "files": {}}
    with tempfile.TemporaryDirectory(prefix=".media-separate-", dir=output_dir) as temporary:
        temp = {key: Path(temporary) / name for key, name in names.items()}
        run(ffmpeg, ["-n", "-i", source, "-map", "0:v:0", "-c:v", "copy", "-an",
                     "-movflags", "+faststart", temp["silent_video"]])
        audio_args = ["-n", "-i", source, "-map", "0:a:0", "-vn", "-c:a", "copy"]
        if extension == ".m4a":
            audio_args += ["-movflags", "+faststart"]
        run(ffmpeg, [*audio_args, temp["original_audio"]])
        if args.mp3:
            run(ffmpeg, ["-n", "-i", source, "-map", "0:a:0", "-vn", "-c:a",
                         "libmp3lame", "-q:a", "2", temp["mp3_audio"]])
        for key, path in temp.items():
            media_type = "video" if key == "silent_video" else "audio"
            info = validate(ffmpeg, path, media_type, metadata)
            entry = {"path": str(destinations[key]), "bytes": path.stat().st_size, **info}
            if key != "mp3_audio":
                stream = "0:v:0" if media_type == "video" else "0:a:0"
                original_hash = packet_hash(ffmpeg, source, stream)
                exported_hash = packet_hash(ffmpeg, path, stream)
                if original_hash != exported_hash:
                    raise RuntimeError(f"Stream copy changed encoded packets: {key}")
                entry["packets_unchanged"] = True
                entry["sha256_packets"] = exported_hash
            result["files"][key] = entry
        for key, path in temp.items():
            publish_exclusive(path, destinations[key])
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
