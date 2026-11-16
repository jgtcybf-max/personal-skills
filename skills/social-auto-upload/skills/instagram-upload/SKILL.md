---
name: instagram-upload
description: 使用 sau CLI 在 Instagram 独立网页登录、立即发布 Reels/单图/轮播、核验原作品并移至最近删除。
license: MIT-0
slug: social-auto-upload-instagram-upload
displayName: Instagram 视频与图文发布
version: 1.0.0
summary: 发布 Instagram Reels、单图或轮播，并核验作品。
---

## 本机执行约定（2026-11-14，用户明确指定）

- 所有浏览器操作只使用真实 Ego（ego-browser），先读取 Ego skill 并运行当前版本的 ego-browser skill。本约定优先于下文默认 Chrome、Camoufox、CloakBrowser、OpenClaw browser、Playwright/Patchright、CDP 专用浏览器等执行路径。
- 上游脚本和说明保留作参考；安装文件不等于已适配 Ego。凡脚本会启动或控制其他浏览器、抽取其他浏览器登录态，均不得直接执行。把需要的页面步骤改用 Ego TaskSpace 的 snapshot、动作、验证完成；无法等价实现时如实说明缺口，不绕过限制。
- 本次仅授权安装，不授权发帖、评论、点赞、收藏、私信或代登录。实际对外操作按当次用户请求执行；不得把安装视为长期账号运营授权。
- 纯本地排版、文件处理、命令帮助和不涉及浏览器的公开 HTTP 读取可按需使用；不自动导入账号凭据、不输出密钥、不自动调用付费服务。
- 本批组件与命令路径已补齐。执行本地 Python/Node/媒体/OCR 命令前可点加载 `C:\Users\TTT\.local\share\ops-skills-20261114\Activate-Tools.ps1`；仅作用于当前 PowerShell 进程。
- Windows 命令使用绝对路径。需要 Python 时使用本技能根目录（子技能向上查找）的 LOCAL_INSTALL.md 指定的解释器，不依赖 python3/uv 在 PATH 中存在。


# Instagram 独立网页发布

调用现有 CLI，不自行实现浏览器上传。使用工程 Patchright Chrome 和独立 Instagram 会话，不使用 Business Suite 的绑定入口。默认可见浏览器，未配置代理时按系统网络直连；需要代理时显式使用 `--proxy` 或设置 `SAU_INSTAGRAM_PROXY`。传 `--proxy ""` 可忽略环境变量并直连。

```powershell
sau instagram login --account creator
sau instagram check --account creator
sau instagram upload-video --account creator --file videos/demo.mp4 --thumbnail covers/demo.png --title "标题" --desc "正文" --tags 生活,分享 --result .local/instagram-video.json
sau instagram upload-note --account creator --images images/1.jpg images/2.jpg --title "轮播标题" --note "正文" --result .local/instagram-images.json
```

视频/Reel 可用 `--thumbnail` 指定 JPG/JPEG/PNG 封面；省略时使用 Instagram 默认封面。指定图片后会检查主预览确实使用该图片，失败则停止提交。封面按当前视频画幅居中裁剪，图片边缘的重要文字应留出安全区域。图文发布不接受此参数。

账号文件保存为 `cookies/instagram_creator.json`。密码和验证由用户在工程浏览器输入。上传流程会自动跳过首次通知提示、确认 Reels 介绍，没有提示则继续。登录验证仍由用户完成；未知弹窗或提示关闭失败须报告，不能宣称上传成功。

视频支持 MP4/MOV，照片支持 JPG/JPEG/PNG/AVIF/HEIC/HEIF，实际处理取决于平台。多图按输入顺序发布轮播，单图和两图轮播已实测。标题、正文、标签合计最多 2200 字符。当前账号独立网页版的照片/Reels 表单及高级设置没有定时入口，当前 CLI 仅支持立即发布；不能把定时任务转换成立即发布。地点、协作者、AI 标签、替代文字、滤镜、裁剪、声音和评论/点赞设置未接入，沿用页面默认值。

最终结果 `published` 代表平台确认作品创建，返回作品编号、原作品链接和媒体数。`processing` 表示已受理且仍在处理，`submission_unknown` 表示提交后结果未确认；不能当成已发布，也不能直接重发。默认结果位于 `.local/instagram-results/`，使用 `--result` 固定记录路径。

```powershell
sau instagram verify --account creator --post-url "原作品链接" --expected-text "原作品中的准确文字" --result .local/instagram-verify.json
sau instagram delete --account creator --post-url "原作品链接" --expected-text "原作品中的准确文字" --result .local/instagram-delete.json
```

结果未知但没有链接时，先在同一账号主页按素材、配文和发布时间找原作品，复制链接再运行 `verify`；未找到不证明失败，不重复上传。链接支持 `/p/编号/`、`/reel/编号/` 和带作者名的形式。核对登录用户、作者、作品编号和正文后才允许删除。删除返回 `deleted`，作品进入“最近删除”；批量删除和提前永久清空不在范围内。本地素材不会删除。`deletion_unknown` 须先查询原作品和“最近删除”，不重复提交删除。

完整参数和能力边界以 `sau instagram upload-video --help`、`upload-note --help`、`verify --help` 和 `delete --help` 为准。失败时根据结果文件中的错误及本地证据分析；不得把账号状态、截图或页面记录提交到 Git。

## 示例脚本

`scripts/examples/` 下的文件是复制用示例，不是运行时依赖。执行前先查看当前 CLI 的 `--help`，替换账号、素材和正文；这些命令可能创建真实作品。

- `instagram_commands.ps1`：PowerShell
- `instagram_commands.sh`：Bash
- `instagram_cli_template.py`：Python subprocess
