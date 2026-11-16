# 小红书 MCP 本机安装

- 原仓库：https://github.com/xpzouying/xiaohongshu-mcp
- 固定提交：bb6fa2e208719ee634fec37881be29d3aa4699b3
- 从官方源码本机构建，源码内容未修改；Git blob SHA1 校验 83 个构建相关文件。
- 编译工具：Go 1.27.3，便携安装，官方工具链 SHA256 校验通过。
- 主程序：`C:\Users\TTT\.local\share\ops-skills-20261114\xiaohongshu-mcp\bin\xiaohongshu-mcp-windows-amd64.exe`
- 上游登录工具：`C:\Users\TTT\.local\share\ops-skills-20261114\xiaohongshu-mcp\bin\xiaohongshu-login-windows-amd64.exe`
- 主程序构建版本：`bb6fa2e208719ee634fec37881be29d3aa4699b3-local`；两个程序 `-h` 均通过。
- 选定的上游 MCP 协议、工具注册、参数校验、路由、配置单测已通过；这些测试不启动浏览器或登录账号。
- Codex 已保存 HTTP MCP 配置：`http://127.0.0.1:18060/mcp`，`enabled=false`。
- 默认服务启动时下载专用 Chromium，实际操作用 go-rod；当前版本没有 Ego 执行后端。按用户只用真实 Ego 的要求，服务保留停用，不执行该启动或登录工具。未安装上游专用浏览器，也没有把 Ego 伪装为其 Chromium 路径。
- 不将“程序已经安装”描述为“Ego 已接入 MCP”。网页任务使用真实 Ego skill 执行。

程序哈希和源码校验记录：`C:\Users\TTT\Documents\ChatGPT\工作\work\ops-skills-install-20261114\mcp_install_result.json`。


## 补装完成（2026-11-14）

- 公共运行环境：`C:\Users\TTT\.local\share\ops-skills-20261114`。
- 在 PowerShell 中执行 `. 'C:\Users\TTT\.local\share\ops-skills-20261114\Activate-Tools.ps1'`，仅给当前进程补充 Python/Node/FFmpeg/ffprobe/Tesseract 路径及 UTF-8、语言包设置；未修改系统 PATH。
- Python：`C:\Users\TTT\.local\share\ops-skills-20261114\.venv\Scripts\python.exe`。
- Tesseract：`C:\Users\TTT\.local\share\ops-skills-20261114\tools\tesseract\tesseract.exe`，含 chi_sim/eng；本地 OCR 可用但识别结果仍需校对。
- FFmpeg/ffprobe：`C:\Users\TTT\.local\share\ops-skills-20261114\tools\ffmpeg\bin`。
- B 站上传器：`C:\Users\TTT\.social-auto-upload\tools\biliup\windows-x86_64\biliup.exe`（v1.3.5）。
- SAU 本地文章转换依赖与 Flask、Flask-CORS、xhs 已补装；Agent-Reach 默认 B 站读取命令 bili-cli 已装。
- 小红书 MCP 主程序与登录工具已从固定官方源码编译安装，HTTP 地址登记，enabled=false；上游专用浏览器后端未适配 Ego，所以不启动服务或原登录工具。
- 所有网页操作继续只用真实 Ego；本次安装并未验证真实账号的采集/发布功能。
- 当前安装状态：`C:\Users\TTT\Documents\ChatGPT\工作\work\ops-skills-install-20261114\安装结果.md`。
