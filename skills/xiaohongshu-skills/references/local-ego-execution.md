# 本机小红书执行方式

网页操作只用真实 Ego / ego(lite)。先读 `C:/Users/TTT/.agents/skills/ego-browser/SKILL.md` 并执行当前版本的 `ego-browser skill`，按 TaskSpace → snapshot → action → verification 操作。

- 先用当前快照识别控件，动作后验证页面结果。登录、验证码或设备验证按 Ego 指南 handOff，由用户处理，再恢复同一任务空间。
- 不启动上游 chrome_launcher.py、Camoufox、Playwright 或其他专用浏览器，不提取其他浏览器 Cookie。
- 上游 CLI、原始 SKILL.upstream.txt 保留作参考。依赖 Chrome/XHS Bridge 的脚本尚未接入 Ego，不能直接执行或宣称已完成账号端到端测试。
- 发布、评论、点赞、收藏、退出等行为按本次用户授权执行。已有明确授权且内容账号已确定时，无需重复询问；缺关键内容时先完成可审阅草稿再补齐。
- 标题计数、模板、定时范围、字段与媒体上限以当前官方页面为准；不照搬可能过时的固定值。
- 记录链接、采集时间、样本数及可见字段。缺失数据标注不可用，不把公开累计互动数当作后台时段数据。
- 提交结果未知时先检查原作品/原状态，不重复发送。平台验证或限制出现时停止相关动作，不切换浏览器、后端或账号绕过。

本地 Python：`C:/Users/TTT/.local/share/ops-skills-20261114/.venv/Scripts/python.exe`。纯本地 OCR 模块为本项目 `scripts/image_ocr.py`，不启动浏览器。

2026-11-14 已验证本地中文 OCR；本次去重未登录账号或执行发布、互动，未验证这些页面流程的账号端到端结果。
