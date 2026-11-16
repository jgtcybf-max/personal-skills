---
name: openfilm
description: 使用 OpenFilm 创建或编辑 film.html 视频工程、网页动画、时间线与画布，并在真实 Ego 中预览 Studio。本机固定 0.3.2；原生 Chromium 渲染与导出受 Ego 浏览器要求限制。用于打开 OpenFilm、制作网页视频工程、剪辑时间线或调整图文音轨。
---

# OpenFilm

本机已安装官方 OpenFilm 0.3.2，使用以下固定入口。不要执行 `npx openfilm@latest` 或自行全局更新，以免覆盖本机的 Ego 适配。

```powershell
& 'C:\Users\TTT\.local\share\openfilm-0.3.2\openfilm.ps1'
```

先完整阅读入口打印的手册；按任务读取 `skill edit`、`skill media` 或 `skill canvas`。入口后面直接传参数，例如：

```powershell
& 'C:\Users\TTT\.local\share\openfilm-0.3.2\openfilm.ps1' skill edit
& 'C:\Users\TTT\.local\share\openfilm-0.3.2\openfilm.ps1' open 'C:\Users\TTT\Videos\OpenFilm\Projects\我的视频'
```

每个视频使用独立工程目录。修改前读取工程现有文件，保留 Studio 写入的 overrides 与用户修改。其他命令在对应工程目录运行。

## 浏览器与功能边界

- 网页操作只用真实 Ego。打开 Studio 前读取 `C:\Users\TTT\.agents\skills\ego-browser\SKILL.md` 并运行当前 Ego 的 `skill` 指南；按 TaskSpace → snapshot → action → verification 操作。同一任务复用同一 Space。
- 入口设置 `OPENFILM_NO_BROWSER=1`，不自动打开系统默认浏览器。`open` 打印本地 Studio 地址后，通过 Ego 打开。地址中的本地授权 key 不写入公开报告。
- 可创建和编辑 `film.html`、页面、时间线与画布，并在 Ego 中预览；FFmpeg、ffprobe、Node 与 Git 已有本机入口。
- 上游 `look`、`render`、HTML 缩略图和部分 Studio 导出依赖 Playwright 管理的 Chromium。本机在统一启动点明确阻止其下载和启动，尚无官方 Ego 渲染后端。命令出现 `EGO_ONLY` 应如实说明，不能声称原生导出通过，也不能切换浏览器绕过。
- 如任务只需对已有视频做切分、拼接、音轨处理，可使用本地 FFmpeg；这不等于 OpenFilm 的 HTML 视频导出。不得把检查一张截图当作整个成片已验证。
- 图片、语音、音乐和视频生成服务需要用户自己的服务或账号。安装不代表付费授权，不自动提交付费生成任务。

官方仓库：https://github.com/openfilm/openfilm 。上游原始技能见 `SKILL.upstream.txt`；安装来源、固定版本与限制见 `LOCAL_INSTALL.md`。
