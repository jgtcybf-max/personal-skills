"""Local Windows adaptation, 2026-11-16: resolve existing media binaries.

Original project: AI 创意研究室, AGPL-3.0-only. This helper reads the local
runtime configuration and adds verified installed binaries to this process.
"""
from pathlib import Path
import json
import os
import shutil


def configure_media_path() -> None:
    config = Path(__file__).resolve().parents[1] / "references" / "local-runtime.json"
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    folders = []
    for name in ("ffmpeg", "ffprobe"):
        candidate = Path(data.get(name, ""))
        if candidate.is_file():
            folders.append(str(candidate.parent))
    if folders:
        os.environ["PATH"] = os.pathsep.join(dict.fromkeys(folders + [os.environ.get("PATH", "")]))


def require_media_tools() -> None:
    configure_media_path()
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise SystemExit("Required media executable not found: " + ", ".join(missing))
