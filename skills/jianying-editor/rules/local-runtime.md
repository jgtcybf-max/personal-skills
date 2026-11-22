# Installed Windows runtime

This installation uses [isYangs/jianying-editor-skill](https://github.com/isYangs/jianying-editor-skill), version 1.0.0, commit `b7225641d39a9cd354ec265e2f6101b009fa1b44`. Preserve its MIT license and vendored source attribution.

Use the dedicated Python environment; dependencies are isolated from system Python:

```powershell
$jySkill = Join-Path $env:USERPROFILE '.codex/skills/jianying-editor'
$jyPython = Join-Path $env:USERPROFILE '.local/share/video-edit-runtimes/jianying-editor/Scripts/python.exe'
$env:JY_SKILL_ROOT = $jySkill
& $jyPython -B (Join-Path $jySkill 'scripts/draft_inspector.py') --help
```

The installed launcher sets the skill root and adds the existing FFmpeg/ffprobe binaries to its process PATH:

```powershell
& (Join-Path $jySkill 'scripts/python-runtime.cmd') script.py
```

Use this launcher for project scripts. Put those scripts and generated assets in the user's project directory. The vendored `pyJianYingDraft` library is included; no separate installation of that library is required.

The upstream Windows branch of `JyProject.export_video()` was empty and made the whole module fail to parse. The local fix delegates it to the existing `auto_exporter.auto_export()` and returns success or failure consistently. The upstream version field is retained under `metadata.version` for Codex skill validation.

The author limits automatic export to Jianying 5.9 or earlier. The installed desktop application was 11.8.0.14778 when checked on 2026-11-22. Draft generation checks do not establish that this newer application can open or export every generated draft. Verify the requested workflow in the application before reporting that compatibility is proven.

For new projects, use a fresh name. Read the original initialization and core guides before editing an existing project: the upstream constructor defaults to `overwrite=True`.

Web operations and previews use the user's real Ego browser. Installing the upstream Playwright Python dependency does not select or launch a different browser.
