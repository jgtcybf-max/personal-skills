---
name: xiaohongshu-skills
description: 小红书操作统一入口，按认证、图文视频与长文发布、搜索详情、图片 OCR、互动及复合研究分流。网页操作只使用真实 Ego。
---

# 小红书操作入口

先读 [本机 Ego 执行方式](references/local-ego-execution.md)，再按任务只加载对应子技能。

| 任务 | 读取 |
|---|---|
| 登录、账号状态、切换或退出 | [xhs-auth](skills/xhs-auth/SKILL.md) |
| 图文、视频、长文、草稿或排期 | [xhs-publish](skills/xhs-publish/SKILL.md) |
| 搜索、详情评论、主页或首页 | [xhs-explore](skills/xhs-explore/SKILL.md) |
| 保存图片或识别图片文字 | [xhs-images-ocr](skills/xhs-images-ocr/SKILL.md) |
| 评论回复、点赞或收藏 | [xhs-interact](skills/xhs-interact/SKILL.md) |
| 竞品、热点、选题或组合创作 | [xhs-content-ops](skills/xhs-content-ops/SKILL.md) |

账号定位与长期策略读 `xiaohongshu-ops`；图片制作读 `xhs-note-creator`、`baoyu-xhs-images` 等专项技能。自有创作者后台数据和评论/@通知读 [专项数据参考](references/creator-data-and-notifications.md)。

已合并原 post-to-xhs 与 xiaohongshu-upload 发布入口。上游实现仍保留，但不宣称 CLI 已适配 Ego。
