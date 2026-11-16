---
name: baijiahao-upload
description: 使用 social-auto-upload 的 `sau baijiahao` 登录百家号、检查账号并发布视频。Use when 用户要向百家号发布视频或核验百家号登录状态。
license: MIT-0
slug: social-auto-upload-baijiahao-upload
displayName: 百家号视频发布
version: 1.0.0
summary: 登录百家号并发布视频，支持封面和合集。
---

## 本机执行约定（2026-11-14，用户明确指定）

- 所有浏览器操作只使用真实 Ego（ego-browser），先读取 Ego skill 并运行当前版本的 ego-browser skill。本约定优先于下文默认 Chrome、Camoufox、CloakBrowser、OpenClaw browser、Playwright/Patchright、CDP 专用浏览器等执行路径。
- 上游脚本和说明保留作参考；安装文件不等于已适配 Ego。凡脚本会启动或控制其他浏览器、抽取其他浏览器登录态，均不得直接执行。把需要的页面步骤改用 Ego TaskSpace 的 snapshot、动作、验证完成；无法等价实现时如实说明缺口，不绕过限制。
- 本次仅授权安装，不授权发帖、评论、点赞、收藏、私信或代登录。实际对外操作按当次用户请求执行；不得把安装视为长期账号运营授权。
- 纯本地排版、文件处理、命令帮助和不涉及浏览器的公开 HTTP 读取可按需使用；不自动导入账号凭据、不输出密钥、不自动调用付费服务。
- 本批组件与命令路径已补齐。执行本地 Python/Node/媒体/OCR 命令前可点加载 `C:\Users\TTT\.local\share\ops-skills-20261114\Activate-Tools.ps1`；仅作用于当前 PowerShell 进程。
- Windows 命令使用绝对路径。需要 Python 时使用本技能根目录（子技能向上查找）的 LOCAL_INSTALL.md 指定的解释器，不依赖 python3/uv 在 PATH 中存在。


# 百家号视频发布

调用现有 CLI，不另写上传流程。账号名是本地会话别名；发布前先查看 `sau baijiahao upload-video --help`。

```powershell
sau baijiahao login --account creator
sau baijiahao check --account creator
sau baijiahao upload-video --account creator --file videos/demo.mp4 --title "标题" --desc "简介" --tags 百家号,测试
```

当前仅支持视频，不支持图文和定时发布。可选 `--thumbnail` 指定封面，`--collection` 指定已有合集。先完成百度账号登录并保存会话；登录出现二维码时把二维码图片展示给用户。

发布前核对账号、素材、标题、文案和标签。只有命令及平台提供的本次提交证据才表示成功；超时或状态不明时先去后台核查，不能直接重发。
