# OpenFilm 本机安装

- 官方仓库：<https://github.com/openfilm/openfilm>
- 官网：<https://openfilm.dev>
- 固定版本：0.3.2（2026-11-14 安装）
- 官方技能：`skills/openfilm/SKILL.md`，Git blob `02fa6dae42d9fa855f679579e4417838259d56ff`。
- npm 包：`openfilm@0.3.2`；完整性及本地补丁哈希记录于 `C:\Users\TTT\.local\share\openfilm-0.3.2\installation.json`。
- 运行入口：`C:\Users\TTT\.local\share\openfilm-0.3.2\openfilm.ps1`。
- 依赖：Node 22.22.2、FFmpeg/ffprobe、Git；npm `playwright-core@1.61.1` 作为上游模块依赖安装，但未安装其浏览器，也不允许通过其启动浏览器。

本机三个补丁：统一渲染浏览器启动点抛出 `EGO_ONLY`、禁止自动下载 Chromium、禁止 Studio 打开系统默认浏览器。原始文件保存在运行目录 `upstream-originals`。未安装 Electron 桌面壳；Studio 在真实 Ego 打开。

功能限制：原生 look/render、HTML 缩略图与部分导出不可用；Ego 编辑器和预览需与成片导出分别核验。上游 doctor 会因渲染引擎限制报未就绪，不能将该状态说成全部健康。

安装证据：`C:\Users\TTT\Documents\ChatGPT\工作\work\river-video-tool-20261114`。
