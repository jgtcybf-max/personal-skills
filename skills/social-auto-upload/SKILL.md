---
name: social-auto-upload
description: 为 social-auto-upload 提供总入口，按平台和内容类型选择对应发布流程。Use when 用户要在本仓库支持的平台发布视频、文章或图文，或需要把内容分发到多个指定平台。
license: MIT-0
slug: social-auto-upload
displayName: social-auto-upload 多平台发布入口
version: 1.0.0
summary: 按用户指定的平台和内容类型选择发布流程。
---

## 本机执行约定（2026-11-14，用户明确指定）

- 所有浏览器操作只使用真实 Ego（ego-browser），先读取 Ego skill 并运行当前版本的 ego-browser skill。本约定优先于下文默认 Chrome、Camoufox、CloakBrowser、OpenClaw browser、Playwright/Patchright、CDP 专用浏览器等执行路径。
- 上游脚本和说明保留作参考；安装文件不等于已适配 Ego。凡脚本会启动或控制其他浏览器、抽取其他浏览器登录态，均不得直接执行。把需要的页面步骤改用 Ego TaskSpace 的 snapshot、动作、验证完成；无法等价实现时如实说明缺口，不绕过限制。
- 本次仅授权安装，不授权发帖、评论、点赞、收藏、私信或代登录。实际对外操作按当次用户请求执行；不得把安装视为长期账号运营授权。
- 纯本地排版、文件处理、命令帮助和不涉及浏览器的公开 HTTP 读取可按需使用；不自动导入账号凭据、不输出密钥、不自动调用付费服务。
- 本批组件与命令路径已补齐。执行本地 Python/Node/媒体/OCR 命令前可点加载 `C:\Users\TTT\.local\share\ops-skills-20261114\Activate-Tools.ps1`；仅作用于当前 PowerShell 进程。
- Windows 命令使用绝对路径。需要 Python 时使用本技能根目录（子技能向上查找）的 LOCAL_INSTALL.md 指定的解释器，不依赖 python3/uv 在 PATH 中存在。


# social-auto-upload 总入口

先确认用户指定的平台、内容类型、账号别名和发布方式。用户没有指定平台时先询问，不自行选择目标平台。

## 选择平台入口

| 平台 | 专用 Skill | CLI 平台名 |
| --- | --- | --- |
| 抖音 | `douyin-upload` | `douyin` |
| Bilibili | `bilibili-upload` | `bilibili` |
| 小红书 | `xhs-publish`（统一入口，位于 xiaohongshu-skills） | 网页只用 Ego；旧 sau 上传实现保留作参考 |
| 快手 | `kuaishou-upload` | `kuaishou` |
| 视频号 | `tencent-upload` | `tencent` |
| 百家号 | `baijiahao-upload` | `baijiahao` |
| 大鱼号 | `dayu-upload` | `dayu` |
| 支付宝生活号 | `alipay-upload` | `alipay` |
| 微博 | `weibo-upload` | `weibo` |
| 虎扑 | `hupu-upload` | `hupu` |
| TikTok | `tiktok-upload` | 无 `sau` 命令 |
| 雪球 | `xueqiu-upload` | `xueqiu` |
| YouTube | `youtube-upload` | `youtube` |
| 知乎 | `zhihu-upload` | `zhihu` |
| Facebook 个人主页 | `facebook-upload` | `facebook` |
| Facebook Page | `meta-upload` | `facebook-page` |
| Instagram | `instagram-upload` | `instagram` |

## 工作流程

1. 如已安装对应平台 Skill，先读取并遵循它；从仓库运行时读取 `skills/<skill-name>/SKILL.md`。小红书已合并到 `C:/Users/TTT/.codex/skills/xiaohongshu-skills/skills/xhs-publish/SKILL.md`，不再加载旧 `xiaohongshu-upload` 入口；共享 SAU 实现保留。
2. 若仓库可用，从 `skills/<skill-name>/SKILL.md` 读取平台说明；否则先提供对应安装命令。执行 CLI 前使用 `sau <平台> --help` 确认当前参数。不要猜测参数或声称 TikTok 有 CLI。
3. 先检查目标账号状态；登录需要用户在平台页面完成时，交给用户操作，不索取或保存密码。
4. 发布前核对文件、标题、文案、标签、可见范围、发布时间及目标账号。只发布用户明确指定的平台；同一份内容也要逐个平台核对要求。
5. 只有命令或平台提供本次提交的成功证据才报告已发布。超时或结果未知时先查原作品，不盲目重发。

## 安装入口

从公开 GitHub 仓库安装总入口：

```bash
npx skills add dreammis/social-auto-upload --skill social-auto-upload
```

指定平台时将 `social-auto-upload` 换成表格中的专用 Skill 名称。完整平台能力和分发状态见 GitHub 源仓库的 README 与分发文档。
