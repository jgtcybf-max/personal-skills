---
name: video-splitter
description: Split a local video into a requested number of sequential parts, usually equal-duration segments, while preserving audio and exporting numbered files. Use for requests to divide one video into multiple reusable clips; do not use for content-aware editing or downloading videos.
---

# Video Splitter

Split the supplied local video into sequential clips. Unless the user gives meaningful cut points, interpret a request to split into N parts as equal-duration segments. The default is 5 parts.

Use `scripts/split_video.py` for execution. It locates FFmpeg from `PATH` or the installed `imageio-ffmpeg` package, probes the source duration, re-encodes each segment for accurate boundaries, and keeps the first video and audio streams. The script writes numbered files using the requested prefix.

Workflow:

1. Confirm the input file exists and identify the requested part count, output directory, prefix, and preferred extension. If the user only says to split into parts, use 5, the input file's directory, and a concise numbered prefix based on the request. Non-ASCII prefixes are supported.
2. Run the script. Install `imageio-ffmpeg` only if no system FFmpeg is available and the package is missing.
3. Verify that the expected number of files exists and report their paths and approximate durations. Do not delete or overwrite the original source.

Example:

```powershell
python scripts/split_video.py "C:\path\source.MOV" --count 5 --output-dir "C:\path" --prefix "voice-material"
```

The operation is a temporal split, not a semantic or market-based edit. If the user asks for scene, topic, product, or market-based boundaries, ask for timestamps or explain that equal-duration splitting is the available default.
