# 本机安装说明

- 视频项目：guizang-social-card-skill
- 原仓库：https://github.com/op7418/guizang-social-card-skill
- 固定提交：64d02d435fb092d3b403455a875e842fc8f29b8b
- 安装目录：C:\Users\TTT\.codex\skills\guizang-social-card-skill
- 浏览器：用户指定只用 Ego；上游其他浏览器脚本未自动适配，实际使用应通过 Ego 流程执行。
- Python 基础环境：C:\Users\TTT\.local\share\ops-skills-20261114\.venv\Scripts\python.exe（建立后见安装结果）。
- 原始 skill 内容保留在同目录 SKILL.upstream.txt；包装与说明文件完整保留。
- 本次未登录任何社交账号，未发布或评论。登录与平台权限在实际使用时核验。


## 本机运行状态（最终核验）

- Python：`C:\Users\TTT\.local\share\ops-skills-20261114\.venv\Scripts\python.exe`。
- Windows 控制台运行 Python 命令时设置 `PYTHONUTF8=1`，或使用 `python.exe -X utf8`。
- CLI 使用独立环境中的绝对路径；没有修改系统 PATH。
- Python/Node 依赖已安装；未下载 Playwright/Camoufox 浏览器，不启动上游专用浏览器。
- 完整状态及限制：`C:\Users\TTT\Documents\ChatGPT\工作\work\ops-skills-install-20261114\安装结果.md`。
- Node：`C:\Users\TTT\.workbuddy\binaries\node\versions\22.22.2-6\node.exe`；依赖在本技能 node_modules。
- npm 安装使用 --ignore-scripts；原渲染器尚未适配 Ego，未执行浏览器截图渲染。


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
