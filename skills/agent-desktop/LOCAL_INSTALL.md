# 本机安装

官方来源：<https://github.com/vercel-labs/agent-desktop>。安装日期：2026-11-15（北京时间）。版本：1.3.1，Windows x64。

- 原生程序：`C:\Users\TTT\.local\share\agent-desktop-1.3.1\node_modules\agent-desktop\bin\agent-desktop-win32-x64.exe`。
- 命令入口目录：`C:\Users\TTT\.local\share\agent-desktop-1.3.1`，已加入用户 PATH；新进程生效，现有进程可用绝对路径。
- Codex MCP 名称：`agent-desktop`，stdio 入口为上面的原生程序，参数 `mcp`，已启用。
- Skill：此目录。只注册主技能；Windows 平台及各参考文档由 `agent-desktop skills get platform` 和 `skills get desktop <reference>` 提供，避免重复入口。
- 官方发布 commit：`b0b7277bea09b770ef9d1fb45aad667bc432cd57`。
- npm 官方包以 SHA-512 integrity 和 SHA-1 核对，Windows 可执行文件 SHA-256 与包内侧车核对。

原版技能备份为 `SKILL.upstream.txt`。本机只删除 Codex 不接受的 frontmatter tags/requirements 字段（依赖说明保留在正文），并增加运行路径、Windows 使用及 Ego 网页边界；原生程序没有修改。

验证：version/status、配套指南、独立 WinForms 测试窗口的完整快照、set-value 修改与 get 回读、语义按钮点击与状态确认、关闭测试窗口。全部使用语义 UIA，未启用 headed 或操作用户业务窗口。MCP 初始化、75 个工具的发现与 desktop_status 调用通过。

网页继续使用真实 Ego；本工具用于桌面软件，不可作为绕过 Ego 用户接管或改用其他浏览器的通道。Windows UIPI、高权限窗口、锁屏、Session 0 等限制仍适用，具体应用需要实际核验。

安装清单与证据：`C:\Users\TTT\Documents\ChatGPT\工作\work\agent-desktop-install-20261115`。
