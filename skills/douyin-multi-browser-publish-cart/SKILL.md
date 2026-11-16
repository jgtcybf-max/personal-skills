---
name: douyin-multi-browser-publish-cart
description: 通过真实 Ego 浏览器在抖音创作者中心上传视频、填写文案、添加购物车商品并设置单条或批量排期。支持女鞋情绪文案；仅在用户授权发布后提交。
---

# 抖音挂车发布（Ego，单条与批量）

## Fast Prompt

Ask for or accept this compact prompt:

```text
抖音挂车发布：
账号=目标抖音账号（已知可省略）
视频=本地文件或文件夹
顺序=按文件名/按修改时间/我指定
文案=标题规则或逐条标题；话题
商品=链接或ID；短标题/推荐语
封面=第几秒/默认
排期=立即/定时YYYY-MM-DD HH:mm/第1条立即，第2条+2小时20分，之后每条+1小时
设置=评论开/关，下载开/关，同步否/是
备注=禁忌词/其他要求
```

Minimum fields: `视频`, `文案`, `商品`, `排期`. Verify the target account in Ego before uploading.

For automatic women-shoes emotional copy, the user may write:

```text
文案=随机女鞋情绪文案；#夏日旅行穿搭 #夏日凉鞋分享 #春夏新款
```

When this appears, use `$douyin-womens-shoes-emotion-copy` and randomly choose one body-copy line as the post text/title base. In batch mode, choose a different line for each video when possible.

If `视频` is a folder with one video, publish that video. If it has multiple videos, use batch mode when `排期` describes a batch schedule; otherwise ask the user to choose files/order.

## Browser Selection

- Read `C:/Users/TTT/.agents/skills/ego-browser/SKILL.md`, run the installed `ego-browser skill`, and use its current TaskSpace → snapshot → action → verification workflow.
- Use only real Ego / ego(lite). Open `https://creator.douyin.com/creator-micro/content/upload` in the task's managed page. If Ego is unavailable, diagnose it or report the block.
- Verify the visible account matches the requested target. Existing accounts in another browser do not authorize importing its cookies or switching browsers.
- This skill merges the former `douyin-publish-cart` single-video workflow with batch scheduling and the optional emotion-copy bank. The retained name supports existing invocations; browser operations now use Ego only.

## Safety Rules

- Never ask for passwords. If QR login, phone verification, captcha, or account confirmation appears, ask the user to finish it in the chosen browser.
- Use Ego's documented file chooser or file-input methods for uploads. Observe page state after upload, text fill, product attach, scheduling, and publish; inspect screenshots only when visual evidence is needed.
- Chinese file paths can fail in Windows file picker automation. If needed, copy the video to an ASCII temp path under the workspace and upload that copy.
- Preserve user copy exactly unless they request optimization.
- Default behavior is to stop before final `发布`; click final publish only when the user explicitly says to publish or click publish.

## Publishing Workflow

1. Open Douyin Creator Center upload page in Ego and verify the target account.
2. Upload the video.
3. Fill title and hashtags according to `文案`. If `文案=随机女鞋情绪文案`, use a randomly selected line from `$douyin-womens-shoes-emotion-copy` plus the provided hashtags.
4. Set cover if reliable controls are available; otherwise keep current/recommended cover and report the limitation.
5. Attach shopping cart:
   - Choose `添加标签` -> `购物车`.
   - Paste product link/ID and click add.
   - Fill product short title/recommendation.
   - Verify the page shows `已添加商品（1）`.
6. Set visibility, comments/download/sync/timing according to `设置` and `排期`.
7. Check title, product card, timing, and upload status.
8. Publish only when authorized. Verify success on the result page or作品管理 list.

## Batch Scheduling

Default video order is filename ascending with natural numeric order (`1.mp4`, `2.mp4`, `10.mp4`). If the user says `按修改时间`, sort oldest to newest unless specified otherwise.

For `第1条立即，第2条+2小时20分，之后每条+1小时`, compute from the batch start time:

- Video 1: immediate publish.
- Video 2: start + 2 hours 20 minutes.
- Video 3: start + 3 hours 20 minutes.
- Video 4: start + 4 hours 20 minutes.
- Continue adding 1 hour for each later video.

Convert all relative schedules to exact local date/time before entering them. If a time crosses midnight, use the next calendar date.

Publish each item independently. If upload, cart attach, or schedule validation fails for one item, stop and report which video failed.

If `文案=随机女鞋情绪文案` in batch mode, pick one unused line per video from `$douyin-womens-shoes-emotion-copy`. Pair each selected line with the same hashtag group unless the user provides per-video hashtags.
