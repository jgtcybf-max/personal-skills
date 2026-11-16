---
name: youtube-upload
description: 使用 social-auto-upload 的 `sau youtube` 登录 YouTube 并上传、安排定时或设置视频可见范围。Use when 用户要向 YouTube 发布或定时发布视频，或检查 Google/YouTube 登录状态。
license: MIT-0
slug: social-auto-upload-youtube-upload
displayName: YouTube 视频发布
version: 1.0.0
summary: 使用 sau 登录 YouTube 并上传或定时发布视频。
---

## 本机执行约定（2026-11-14，用户明确指定）

- 所有浏览器操作只使用真实 Ego（ego-browser），先读取 Ego skill 并运行当前版本的 ego-browser skill。本约定优先于下文默认 Chrome、Camoufox、CloakBrowser、OpenClaw browser、Playwright/Patchright、CDP 专用浏览器等执行路径。
- 上游脚本和说明保留作参考；安装文件不等于已适配 Ego。凡脚本会启动或控制其他浏览器、抽取其他浏览器登录态，均不得直接执行。把需要的页面步骤改用 Ego TaskSpace 的 snapshot、动作、验证完成；无法等价实现时如实说明缺口，不绕过限制。
- 本次仅授权安装，不授权发帖、评论、点赞、收藏、私信或代登录。实际对外操作按当次用户请求执行；不得把安装视为长期账号运营授权。
- 纯本地排版、文件处理、命令帮助和不涉及浏览器的公开 HTTP 读取可按需使用；不自动导入账号凭据、不输出密钥、不自动调用付费服务。
- 本批组件与命令路径已补齐。执行本地 Python/Node/媒体/OCR 命令前可点加载 `C:\Users\TTT\.local\share\ops-skills-20261114\Activate-Tools.ps1`；仅作用于当前 PowerShell 进程。
- Windows 命令使用绝对路径。需要 Python 时使用本技能根目录（子技能向上查找）的 LOCAL_INSTALL.md 指定的解释器，不依赖 python3/uv 在 PATH 中存在。


# YouTube 视频发布

调用现有 `sau youtube` CLI。登录在浏览器中完成 Google 账号登录，不使用二维码；账号名是本地会话别名。

```powershell
sau youtube login --account creator
sau youtube check --account creator
sau youtube upload-video --account creator --file videos/demo.mp4 --title "标题" --desc "简介" --tags tag1,tag2 --visibility public
```

标题最多 100 个字符。`--visibility` 可选 `public`、`unlisted`、`private`，默认 `public`；`--thumbnail` 指定封面，`--playlist` 指定已有播放列表。只有用户明确给出定时时间才传 `--schedule "YYYY-MM-DD HH:MM"`；该选项会使用 YouTube Studio 的 Schedule 状态，需核对页面显示的日期与时间。

发布前再次核对账号、视频、标题、说明、标签、可见范围及立即/定时意图。上传或发布遇到超时时先查 YouTube Studio 中的原视频，不盲目重传。上传成功不等于审核完成或公开视频已可播放。
