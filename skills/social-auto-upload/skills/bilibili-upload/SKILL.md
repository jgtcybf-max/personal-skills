---
name: bilibili-upload
description: 当 agent 需要通过已安装的 `sau` CLI 完成 Bilibili 登录、账号校验或视频上传时使用这个 skill。优先使用 `sau bilibili ...`，程序会自动准备 `biliup`，不要求用户手动安装。
license: MIT-0
slug: social-auto-upload-bilibili-upload
displayName: Bilibili 视频发布
version: 1.0.0
summary: 登录哔哩哔哩并发布视频，支持分区选择。
---

## 本机执行约定（2026-11-14，用户明确指定）

- 所有浏览器操作只使用真实 Ego（ego-browser），先读取 Ego skill 并运行当前版本的 ego-browser skill。本约定优先于下文默认 Chrome、Camoufox、CloakBrowser、OpenClaw browser、Playwright/Patchright、CDP 专用浏览器等执行路径。
- 上游脚本和说明保留作参考；安装文件不等于已适配 Ego。凡脚本会启动或控制其他浏览器、抽取其他浏览器登录态，均不得直接执行。把需要的页面步骤改用 Ego TaskSpace 的 snapshot、动作、验证完成；无法等价实现时如实说明缺口，不绕过限制。
- 本次仅授权安装，不授权发帖、评论、点赞、收藏、私信或代登录。实际对外操作按当次用户请求执行；不得把安装视为长期账号运营授权。
- 纯本地排版、文件处理、命令帮助和不涉及浏览器的公开 HTTP 读取可按需使用；不自动导入账号凭据、不输出密钥、不自动调用付费服务。
- 本批组件与命令路径已补齐。执行本地 Python/Node/媒体/OCR 命令前可点加载 `C:\Users\TTT\.local\share\ops-skills-20261114\Activate-Tools.ps1`；仅作用于当前 PowerShell 进程。
- Windows 命令使用绝对路径。需要 Python 时使用本技能根目录（子技能向上查找）的 LOCAL_INSTALL.md 指定的解释器，不依赖 python3/uv 在 PATH 中存在。


# Bilibili 上传 Skill

优先把 `sau` 作为主接口。

不要一开始就让用户自己找 `biliup` 或手动下载 release。
程序会在运行时自动检查、自动下载、自动更新 `biliup`。

## 功能概览

| 功能 | 命令入口 | 说明 |
| --- | --- | --- |
| 登录 | `sau bilibili login --account <name>` | 需要用户自己在本地真实终端里执行，用于生成或刷新登录信息 |
| 校验 | `sau bilibili check --account <name>` | 检查指定账号当前是否有效 |
| 视频上传 | `sau bilibili upload-video ...` | 上传一条 Bilibili 视频 |

## 默认工作流

1. 先确认 `references/runtime-requirements.md`
2. 再确认 `references/cli-contract.md`
3. 执行匹配的 `sau bilibili ...` 命令
4. 如果命令失败，再看 `references/troubleshooting.md`

## 命令选择建议

- 用户没有登录信息，先让用户自己在本地终端执行 `login`
- 用户只想确认账号状态，先用 `check`
- 用户要发视频，用 `upload-video`

## 执行前检查

- 优先确认当前环境能运行 `sau`
- 如果 `sau` 不在 PATH 中，可以用仓库里的 `sau_cli.py`
- 不要要求用户手动下载 `biliup`
- 第一次运行 Bilibili 命令时，程序可能会自动联网准备 `biliup`
- 对 agent 来说，不要在非交互环境里硬跑 `sau bilibili login`
- 正确做法是让用户自己在本地终端执行 `sau bilibili login --account <name>`
- 如果终端里的二维码显示不完整，提醒用户直接打开当前目录下的 `qrcode.png` 扫码

## 参考文档

- 运行前提：`references/runtime-requirements.md`
- CLI 契约：`references/cli-contract.md`
- 故障排查：`references/troubleshooting.md`
