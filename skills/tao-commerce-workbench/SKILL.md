---
name: tao-commerce-workbench
description: 酷酷酷酷的涛的个人技能工作台。检索本机Codex与WorkBuddy的影像导演、视频、电商、发布、开发、文档和效率技能，并补查外部电商技能目录。用于“我的技能库”“我的电商工作台”“本机有哪些工具”“选哪个技能”及需要串联工具的任务；单一明确任务直接用对应技能。
---

# 酷酷酷酷的涛 · 技能工作台

把已有工具串成能交付的日常流程，优先本机工具；外部目录用于补缺。个人品牌是定制工作台的署名，第三方工具的原作者、版本和许可保留在目录与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 本机完整目录

[references/local-tools.json](references/local-tools.json) 收录当前本机的 Codex 与 WorkBuddy 技能，以及实际提供的系统/插件入口。按名称、中文标题或分类搜索；`--local-only` 仅查本机。每项保留原始路径、所属客户端及文件校验值。同一物理文件的软链接合并，同名不同内容的版本分别保留。WorkBuddy入口不代表已经注册到Codex；先读取原文，核对专属工具。收录不改变技能原作者归属。

## 女鞋业务项目

用户要求按自己的女鞋工作场景统筹执行时，读取 [references/shoe-operations.md](references/shoe-operations.md)，进入已创建的“涛的女鞋运营”项目：按需分工、一批一份记录、稳定版本存档。简单派单直接完成，不扩大为生产/发布。

## 先匹配任务

已有输入足够就执行；缺少关键商品/模板/素材时只询问影响结果的信息。单项任务直接读对应工具的 SKILL.md。需要多个步骤时按下表选一条，读取 [references/workflows.md](references/workflows.md) 对应章节的输入、路由和验收条件。

| 场景 | 工作流 | 优先入口 |
|---|---|---|
| 选款、竞品、找货与成本 | 女鞋选款与货源核价 | douyin-shop-sales-ranking、douyin-product-image-export、Ego |
| 拼多多/抖音同款SKU与图片表 | 同款审核与商品资料包 | pdd-douyin-review-fill、shoe-template-image-fill |
| 参考视频改成我的鞋 | 参考视频转女鞋脚本 | video-master（完整剧本故事板）、rea-video（来源包装）、douyin-shoe-video-recreate（换鞋/脚本） |
| 货号与参考链接派给剪辑 | 每日剪辑派单与挂车排期 | daily-editing-tasks、douyin-video-download |
| 女鞋小红书图文/封面 | 女鞋种草选题与图文 | xhs-content-ops、xhs-visual-director、xhs-note-creator |
| 利润、投放、经营或工作结果 | 经营利润与投放复盘 | spreadsheets:Spreadsheets、Ego |

这六条是根据用户日常任务与本机工具提炼的个人流程，不代表逐一蒸馏或安装了161个第三方Skill正文。目录里“方法指导”“数据查询”“店铺操作”能力不同。

## 查工具与打开网页

```powershell
& 'C:/Users/TTT/.workbuddy/binaries/node/versions/22.22.2-6/node.exe' 'C:/Users/TTT/.codex/skills/tao-commerce-workbench/scripts/search.mjs' --query '女鞋参考拆解' --limit 3
```

- `--local-only` 只查本机入口，`--external-only` 只查外部目录；默认本机结果在前。
- `--workflows` 读取全部六条流程；`--workflow <id>` 读取单条。流程来源和可选第三方工具在 JSON 中保留。
- `--show-web` 返回本机真实网页路径；直接链接到返回的 `welcome.path`。不要捏造网络地址。页面可离线浏览，使用真实 Ego 验证或操作。
- `--offline` 完全不联网；默认每24小时最多检查一次上游公开目录，断网回退。更新只同步外部目录数据与个人网页列表，不替换个人品牌、工作流和程序。上游代码更新需合并评估。
- 结果为“本机已装入口”只表示文件存在。读取具体技能并核对依赖；外部记录需要安装及可能的账号/API，不能说已经可用。

## 与用户工作保持一致

- 网页只用真实 Ego；先读其当前技能指南，按 TaskSpace、snapshot、操作、核验执行。不得绕过用户接管、验证码或改用其他浏览器。
- 商品材质与卖点只用已确认事实。画面外观与未确认的皮革/PU成分分开；视频生成提示词先写目标素材，再写替换、动作和场景。
- 销量注明时间、来源和口径。没有七日证据就交付快照；累计销量、点赞等不能改称七日销量，未知不填0。
- 本地音频提取默认MP3。日常AI视频产出使用北京时间目录 `C:/Users/TTT/Desktop/ai每日产出/M月D号/`，保留原下载与审核证据。
- 实际发布、联系他人、采购支付或付费生成以当前用户授权为准，安装本工作台不扩大这些范围。已授权的工作持续完成，不因流程文字反复索要确认。
- 交付真实文件、可核验链接和未解决项；未实测的步骤不写成成功。
