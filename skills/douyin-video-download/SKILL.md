---
name: douyin-video-download
description: 下载抖音作品视频到本地文件夹，支持复制的分享文案和短链接，选择原生 1080P 等清晰度并核验文件。用于抖音视频下载，不用于商品图片导出或发布作品。
---

# 抖音视频下载

从分享文案中提取 URL，按用户指定目录和清晰度下载实际视频。未指定目录时询问或使用当前明确的任务目录；不要把过去使用的桌面目录当作永久偏好。用户说“1K”时，可说明按 1080P 理解，并选择短边约 1080 的原生档位。保留竖屏的原始比例，不强制裁剪到 1080×1920。

用户已指定后续默认要求：**无水印、最高可用原生画质**。优先获取平台提供的无水印源，在可获取的完整视频源中比较实际分辨率、码率及压缩观感，选择画质最高的版本，不把1080P当作固定上限。拿不到无水印或更高清源时明确说明实际限制，不把尚未核验的文件称为无水印最高画质。该默认规则仍服从用户当次明确指定的清晰度。

## 获取视频源

1. 可先运行 `yt-dlp --no-playlist --list-formats <URL>`，解析短链接并检查格式。可用时直接用它选择目标档位下载。
2. 如果返回 `Fresh cookies`、403 等，改用可用的真实浏览器打开作品页。使用浏览器自动化时读取适用的浏览器技能。优先现有可用工具；终端没有 npx 不代表浏览器 MCP 也不可用。不要为了下载关闭用户浏览器或修改全局配置。
3. 确认作品 ID、作者和标题与分享内容相符。页面播放的 `video.currentSrc` 可能只是自适应低清源，不应直接当作最高画质。
4. 页面 `RENDER_DATA` 可能没有视频数据。可从视频元素的 React fiber 祖先读取 `memoizedProps.awemeInfo.video`。只返回目标视频字段，不输出整个 props、页面状态、认证信息或巨量 JSON。

可用于页面 evaluate 的紧凑提取代码：

```javascript
() => {
  for (let el = document.querySelector('video'), i = 0; el && i < 6; el = el.parentElement, i++) {
    const key = Object.keys(el).find(k => k.startsWith('__reactFiber'));
    for (let f = el[key], j = 0; f && j < 24; f = f.return, j++) {
      const a = f.memoizedProps?.awemeInfo;
      if (!a?.video) continue;
      const v = a.video;
      return {
        id: a.awemeId, title: a.desc, author: a.authorInfo?.nickname,
        durationMs: v.duration,
        formats: (v.bitRateList || []).map(b => ({
          width: b.width, height: b.height, bytes: b.dataSize,
          bitrate: b.bitRate, gear: b.gearName,
          urls: (b.playAddr || []).map(p => p.src)
        })),
        primary: {width: v.width, height: v.height, bytes: v.dataSize,
          urls: (v.playAddr || []).map(p => p.src)}
      };
    }
  }
  return null;
}
```

若结构变化，检查目标视频附近的字段或页面实际网络响应，调整读取方式。不要假设固定 CDN、签名 URL、作品 ID 或 React 层数永远有效。签名源应现取现用。

## 选档与保存

- 优先选目标原生分辨率；同分辨率可按码率和编码兼容性选择。已验证 `normal_1080_0` 可以是 H.264 MP4，但每次仍以当前源为准。
- 没有用户要求的原生档位时，说明可用最高分辨率；不要把低清放大后声称为原生 1080P。
- 默认无水印要求应通过选择无水印视频源满足；不擅自用裁切、模糊、遮盖或修补改变画面来冒充无水印原片。无水印并不意味着移除原画面已有的商品标识或烧录字幕；对已嵌入画面的标记说明实际情况。
- Windows 可用 `curl.exe --fail --location --retry 2 --referer 'https://www.douyin.com/' --output <临时文件> <源URL>`，命令参数应正确引用。首个源失败可尝试当前格式的备用 URL。
- 使用简短合法文件名，包含作者或标题、清晰度和作品 ID。先下载到同目录的唯一 `.part.mp4`，成功核验后移动到最终文件名。不要覆盖已有文件。
- 只创建用户指定目录及本次下载文件；不要额外保存整页、cookies 或调试日志到交付目录。

## 核验与交付

用 ffprobe 或可用的 OpenCV 检查实际宽高、时长和可解码帧；有条件时确认音轨。对比源的文件字节数（如果提供），防止保存的是错误页或不完整文件。失败的下载不要报告成功。

核对当前可用清晰度列表与实际下载尺寸；查看覆盖开头、中段、结尾及不同角落的画面，检查是否仍有平台浮动水印。记录检查范围和不确定项，不把源URL或文件名包含“无水印”当成画面验证。素材准备时完整静音视频优先复制视频流，避免因拆音轨降低画质；完整音频另存MP3，剪辑版配套音频使用同一剪点。

最终简短告知实际清晰度、尺寸、时长和绝对路径文件链接。若只有较低清晰度，明确说明。
