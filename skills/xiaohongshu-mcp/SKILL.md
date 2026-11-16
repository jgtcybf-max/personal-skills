---
name: xiaohongshu-mcp
description: 小红书 MCP 项目的本机安装入口与连接说明；用于核对服务安装、配置和项目文档。浏览器操作只允许 Ego；主程序与登录工具已本机构建安装，服务因 Ego 后端尚未适配而停用。
---

# 小红书 MCP 本机入口

## 本机执行约定（2026-11-14，用户明确指定）

- 所有浏览器操作只使用真实 Ego（ego-browser），先读取 Ego skill 并运行当前版本的 ego-browser skill。本约定优先于下文默认 Chrome、Camoufox、CloakBrowser、OpenClaw browser、Playwright/Patchright、CDP 专用浏览器等执行路径。
- 上游脚本和说明保留作参考；安装文件不等于已适配 Ego。凡脚本会启动或控制其他浏览器、抽取其他浏览器登录态，均不得直接执行。把需要的页面步骤改用 Ego TaskSpace 的 snapshot、动作、验证完成；无法等价实现时如实说明缺口，不绕过限制。
- 本次仅授权安装，不授权发帖、评论、点赞、收藏、私信或代登录。实际对外操作按当次用户请求执行；不得把安装视为长期账号运营授权。
- 纯本地排版、文件处理、命令帮助和不涉及浏览器的公开 HTTP 读取可按需使用；不自动导入账号凭据、不输出密钥、不自动调用付费服务。
- 本批组件与命令路径已补齐。执行本地 Python/Node/媒体/OCR 命令前可点加载 `C:\Users\TTT\.local\share\ops-skills-20261114\Activate-Tools.ps1`；仅作用于当前 PowerShell 进程。
- Windows 命令使用绝对路径。需要 Python 时使用本技能根目录（子技能向上查找）的 LOCAL_INSTALL.md 指定的解释器，不依赖 python3/uv 在 PATH 中存在。


原项目：https://github.com/xpzouying/xiaohongshu-mcp

官方固定提交的 Go 源码、主程序、登录工具均已安装：C:\Users\TTT\.local\share\ops-skills-20261114\xiaohongshu-mcp

本机安装与路径说明：C:\Users\TTT\.local\share\ops-skills-20261114\xiaohongshu-mcp\LOCAL_INSTALL.md

Codex MCP 地址已登记为 http://127.0.0.1:18060/mcp，enabled=false。主程序/登录工具的命令入口检查及选定的 MCP 协议和注册单测通过。当前默认服务启动时会准备非 Ego 专用浏览器，尚未支持用户指定的真实 Ego，因此不启动；不能声称已完成 Ego 接入。

发布工作流统一读取 `C:/Users/TTT/.codex/skills/xiaohongshu-skills/skills/xhs-publish/SKILL.md`。实际网页任务读取真实 Ego skill 并通过 Ego TaskSpace 执行，保持现有登录会话；不运行上游登录程序，不把安装请求当作账号操作授权。
