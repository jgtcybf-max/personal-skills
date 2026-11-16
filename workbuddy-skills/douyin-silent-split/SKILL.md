---
name: douyin-silent-split
description: 把抖音分享链接或本地 MP4 处理成「无音轨静音视频 + 独立 MP3 音频」并归档到同行素材库。当用户要求下载抖音视频并让视频静音、把音频单独导出为 mp3、分文件夹存放素材，或继续收集同行穿搭/竞品短视频时使用。给出抖音分享口令并要求保存素材时，优先调用本 skill 而非通用下载能力。
agent_created: true
---

# 抖音素材拆分与归档

## 目的

把一条抖音视频（分享口令/链接，或本地 MP4）一次处理成两份可独立使用的素材：

- **静音视频**：真去掉音轨的 MP4（`-c:v copy -an`），视频流不重编码、无画质损失
- **独立音频**：MP3（`libmp3lame -q:a 2`），与视频同名配对

原始带音轨文件只在临时目录里中转，处理完即清理，不在素材库留下重复文件。

## 何时使用

- 用户给出抖音分享口令/链接并要求保存、收集同行素材
- 用户明确要求视频静音、音频单独导出 mp3、分文件夹归档
- 用户给出一个本地 MP4，要求按同一套规则拆分
- 用户说「接下来的视频都这么处理」「按之前的规则处理」时，直接沿用本 skill 的默认参数，不再追问

**不使用**：用户只想要视频内容摘要、仿写文案、分析选题（走对应的文案 skill）；用户明确说「这次要原版带声音的视频」。

## 默认规则（不要每次重新确认）

| 项 | 默认值 |
|---|---|
| 素材库根目录 | 默认 `~/Desktop/同行视频/<M月D号>/`（按当前用户桌面推导，取运行当天）；可用环境变量 `DOUYIN_MATERIAL_ROOT` 覆盖根目录 |
| 布局 | `per-item`：每条素材一个 `<标题>-<awemeId>\` 子目录，内含同名 mp4 + mp3 |
| 命名 | `<标题>-<awemeId>.mp4` 与 `<标题>-<awemeId>.mp3`，同名一一对应 |
| 原始带音轨文件 | 不保留，临时目录中转后删除 |
| 备用布局 | `--layout flat`：静音 MP4 放根目录、MP3 统一放 `音频\`（旧行为，仅特殊需要时用） |

用户明确要求「一个链接一个文件夹」，这是默认行为，**不要平铺到根目录，也不要统一塞进 `音频\`**。`11月5号`、`11月6号` 等日期目录下已形成该结构，保持一致。

## 最高画质（默认开启）

`--quality highest`（默认）会让下载脚本先枚举 `aweme_detail.video.bit_rate`，从页面非登录态正常返回的档位里挑最高一档；若该档无音轨，尝试与独立音频轨用 ffmpeg `-c copy` 无损合流，保证传给拆分环节的仍是带音轨单文件 MP4。拆分环节 `-c:v copy -an` 不做重编码，因此**画质只由下载阶段的选流决定，改拆分参数不会提升画质**。

| 项 | 说明 |
|---|---|
| 默认值 | `highest`；`--quality auto` 退回下载脚本原有的渐进式单文件通道 |
| 排序依据 | `width*height` → `gear_name` 里的档位数字 → `quality` → `bitrate` → 原始顺序。真实抖音常只返回 `gear_name`（如 `normal_1080_0`），此时靠档位数字排序 |
| 输出字段 | `quality`：`gearName` / `candidates`（候选档数）/ `selectionBasis`（实际生效的排序依据）/ `topCandidates`（前三档）/ `mergedWithAudio` |
| 降级 | 最高档取流或合流失败时自动退回默认档，并在 `warnings` 提示「未能取到最高画质档位」。**不要因 `ok: true` 就认定取到了最高档**，要读 `strategy` 与 `quality` |
| ffmpeg | 合流需要 ffmpeg，脚本自动把 `DOUYIN_FFMPEG_PATH` 指向 `bin/ffmpeg.exe` |

边界：只取页面正常返回的档位，不模拟登录、不绕过权限；最高档仍是平台官方流、**带水印**。档位名称不等于成品实际分辨率，需要确切结论时用 `ffmpeg -i` 复核输出流。

## 执行方法

在用户级 skill 目录下执行 `scripts/split_douyin_video.mjs`（Node 22+）。

下载并拆分（最常用，整段分享口令原样用双引号传入）：

```bash
node "C:/Users/TTT/.workbuddy/skills/douyin-silent-split/scripts/split_douyin_video.mjs" \
  "7.61 复制打开抖音，看看【某作者的作品】标题 # 话题 https://v.douyin.com/xxxxxxx/ ..."
```

指定根目录或改用子目录布局：

```bash
node ".../split_douyin_video.mjs" --out-dir "D:/somewhere" --layout per-item "<分享文本>"
```

只拆分已有本地文件、不下载：

```bash
node ".../split_douyin_video.mjs" --input "C:/Users/TTT/Desktop/同行视频/某视频.mp4"
```

只导出音频、或只保留前 N 秒（不必再手工起临时目录分步处理）：

```bash
node ".../split_douyin_video.mjs" --audio-only "<分享文本>"
node ".../split_douyin_video.mjs" --audio-only --trim 59 "<分享文本>"
```

同名文件已存在时**默认不覆盖**，自动追加 `_2`、`_3`（视频与音频共用同一后缀，保持配对）；确需覆盖才加 `--force`。

查看参数：`node ".../split_douyin_video.mjs" --help`

执行后**必须读 stdout 的 `ok` 字段**判断成败，不要只看退出码；`warnings` 非空时如实转述给用户。进度与诊断走 stderr，其中「移动端路径失败」是下载 skill 的正常回退提示，不代表整体失败。

## 输出字段

| 字段 | 说明 |
|---|---|
| `ok` | 是否成功产出静音视频 |
| `title` / `author` / `awemeId` / `description` / `durationText` | 视频元信息（本地文件模式下部分为空） |
| `strategy` | `download-then-split`（下载后拆）或 `local-split`（本地拆） |
| `layout` | 本次使用的布局 |
| `audioOnly` / `trimSeconds` | 是否只导音频、是否截取了前 N 秒 |
| `archive` | 归档自检结果：`dayDir`（日期目录）、`itemDir`（素材子文件夹）、`paired`（mp4/mp3 是否同名同层，`audio-only` 时为 `null`）、`renamed`（是否因重名改过名） |
| `videoPath` / `audioPath` | 两个成品的绝对路径；`audioOnly` 时 `videoPath` 为 `null`；`audioPath` 为 `null` 表示源无音轨或音频导出失败 |
| `videoSizeMB` / `audioSizeMB` | 文件大小 |
| `warnings` | 下载回退、无音轨、MP3 失败、重名改名等说明 |

`archive.paired` 为 `false` 且 `layout` 是 `per-item` 时，说明归档结构异常（两者没落在同一文件夹或不同名），必须检查后再交付。这是为了防止「文件下好了但没按规则归档」这类错误。

交付时把 MP4 与 MP3 两个路径都展示给用户，并说明视频已去音轨、音频为独立 MP3。

## 依赖

| 依赖 | 位置 / 说明 |
|---|---|
| Node.js 22+ | 运行入口脚本 |
| ffmpeg | 内置于 `bin/ffmpeg.exe`（来自 npm `@ffmpeg-installer/win32-x64` 4.1.0，ffmpeg N-92722，含 libmp3lame）。查找顺序：`DOUYIN_FFMPEG_PATH` → `FFMPEG_PATH` → `bin/ffmpeg.exe` → PATH |
| douyin-video-download | 下载环节调用其 `scripts/download_douyin_video.mjs`，查找顺序：`DOUYIN_DOWNLOAD_SCRIPT` → 同级 skill 目录 → `~/.workbuddy/skills/` |
| ffprobe | 不需要。音轨探测用 `ffmpeg -i` 的输出解析 |

mp3 是有损二次编码（AAC → MP3）。做参考、转文案够用；若之后需要原始音质，另行保留 m4a，不要靠 MP3 反推。

## 合规边界

沿用 `douyin-video-download` 的边界：仅限单个/少量视频、个人学习与内部同行参考。不去除水印、不绕过作者禁止下载的设置、不按账号或话题批量抓取、不把能力包装成对外下载服务。音频被单独抽出后更容易被误用，交付时提醒用户不要二次分发或商用。

## 异常处理

| 现象 | 处理 |
|---|---|
| `error` 含「未找到 ffmpeg」 | 检查 `bin/ffmpeg.exe` 是否被移动；或用 `DOUYIN_FFMPEG_PATH` 指定 |
| `error` 含「未找到 douyin-video-download」 | 确认该 skill 已安装，或用 `DOUYIN_DOWNLOAD_SCRIPT` 指定脚本路径 |
| `error` 含「下载失败」 | 读下载 skill 的原始错误；多为风控或网络，稍后重试一次，不要反复重试 |
| `audioPath` 为 `null`，warnings 提示无音轨 | 源本身无音轨，静音视频仍有效，如实告知 |
| `error` 含「生成静音视频失败」 | 检查源文件是否损坏、磁盘是否可写、路径是否含被清洗后仍非法的字符 |
