"""Local OpenMontage registry bridge. No upstream code is bundled."""

import argparse
import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["doctor", "list", "run"])
    parser.add_argument("tool", nargs="?")
    parser.add_argument("--params-file", type=Path)
    args = parser.parse_args()
    config_path = Path.home() / ".local/share/video-edit-runtimes/registry.json"
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    install = config["openmontage"]
    python = Path(install["python"]).resolve()
    root = Path(install["root"]).resolve()
    if not python.is_file() or not (root / "tools/tool_registry.py").is_file():
        raise RuntimeError("OpenMontage registration has missing installation paths")
    os.environ["PATH"] = os.pathsep.join(config["path_entries"] + [os.environ.get("PATH", "")])
    os.environ["PYTHONUTF8"] = "1"
    if Path(sys.executable).resolve() != python:
        return subprocess.call([str(python), "-X", "utf8", str(Path(__file__).resolve()), *sys.argv[1:]])
    params = None
    if args.command == "run":
        if not args.tool or not args.params_file:
            parser.error("run requires a tool and --params-file")
        params = json.loads(args.params_file.resolve().read_text(encoding="utf-8-sig"))
        if not isinstance(params, dict):
            parser.error("params file must contain a JSON object")
    sys.path.insert(0, str(root))
    os.chdir(root)
    with contextlib.redirect_stdout(sys.stderr):
        from tools.tool_registry import registry
        registry.discover()
    if args.command == "doctor":
        executables = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe", "node")}
        result = {"root": str(root), "python": sys.executable,
                  "registered_tools": len(registry.list_all()), "executables": executables,
                  "cloud_services_tested": False}
        success = all(executables.values())
    elif args.command == "list":
        result = {"tools": sorted(registry.list_all())}
        success = True
    else:
        tool = registry.get(args.tool)
        if tool is None:
            raise RuntimeError(f"Unknown tool: {args.tool}")
        with contextlib.redirect_stdout(sys.stderr):
            executed = tool.execute(params)
        result = {"success": executed.success, "data": executed.data, "error": executed.error}
        success = executed.success
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
