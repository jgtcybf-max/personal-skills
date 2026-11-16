# 素材实测与阈值判读

## 一、命令

```bash
# 基本信息
ffmpeg -hide_banner -i "<video>" 2>&1 | grep -E "Duration|Stream"

# 每秒一帧 + 拼图总览
mkdir -p "<out>"
ffmpeg -hide_banner -loglevel error -i "<video>" -vf "fps=1,scale=480:-1" "<out>/f_%02d.jpg"
ffmpeg -hide_banner -loglevel error -i "<out>/f_%02d.jpg" -vf "tile=5x4" -frames:v 1 "<out>/sheet.jpg"

# 关键秒的原尺寸帧
ffmpeg -hide_banner -loglevel error -ss <t> -i "<video>" -frames:v 1 "<out>/k_<t>.jpg"

# 主体区域裁切（按需要改 crop 参数）
ffmpeg -hide_banner -loglevel error -ss <t> -i "<video>" -vf "crop=1080:560:0:1320" -frames:v 1 "<out>/crop.jpg"

# 放大看细节
ffmpeg -hide_banner -loglevel error -i "<frame>.jpg" -vf "crop=520:620:330:150,scale=1040:-1" -frames:v 1 "<out>/zoom.jpg"

# 首帧 / 末帧（查水印）
ffmpeg -hide_banner -loglevel error -ss 0 -i "<video>" -frames:v 1 "<out>/first.jpg"
ffmpeg -hide_banner -loglevel error -sseof -0.1 -i "<video>" -frames:v 1 "<out>/last.jpg"

# 镜头切换点（阈值按需要调，画面变化小的片用 0.08）
ffmpeg -hide_banner -i "<video>" -vf "select='gt(scene,0.08)',metadata=print:file=-" -an -f null - 2>/dev/null | grep pts_time

# 无损/近无损切段
ffmpeg -hide_banner -loglevel error -ss 0 -t <dur> -i "<video>" -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -an "<out>/seg1.mp4"
```

Windows 下若 `ffmpeg` 不在 PATH，先找：`which ffmpeg`、`ls ~/AppData/Local/Programs/Python/Python312/Scripts`。

## 二、像素尺寸怎么算

不要目测「大概占五分之一」。按下面算，报告里给具体数字：

1. 裁出主体所在区域，记下裁切的 `w:h`
2. 在裁切图上量出主体高度占裁切高的比例 `r`
3. 主体像素高 = 裁切输出高 × `r`（换算回原片时再乘缩放比）

更快的办法：主体系数法。已知实物高度 `H_cm`（鞋约 45cm、人约 170cm、杯约 10cm），量画面中该物的像素高 `h_px`，则 `px/cm = h_px / H_cm`。之后任何细节（拉链宽 1cm、鞋底厚 3.5cm）都能直接换算成像素，一眼判断能不能要求。

## 三、阈值表

| 主体像素高（1080p 素材） | 可以要求 | 不可以要求 |
|---|---|---|
| < 200px | 颜色、材质倾向、整体轮廓 | 纹路、文字、五金件、缝线、拉链齿 |
| 200–500px | 加：部件位置、分件数量、大块结构 | 纹理细节、可读文字、品牌刻字 |
| > 500px | 加：局部细节、明线、印字 | 依然慎用「必须可读的文字」 |

经验数字：一行高度 < 12px 的文字，任何视频模型都会吐乱码。所以「字口清晰的 230(1.5)」在 8px 高的区域里，属于不可能完成的要求。

## 四、判读口径

**时长**：视频参考总时长上限 15 秒。超了就分段，切点选在真实镜头切换点上，不要硬切在中途——中途切会产生两段都不完整的动作。

**遮挡与裁切**：一个主体如果在一半以上的帧里被画面边缘裁掉或被其他物体挡住，就不要再要求「完整呈现其背面/底面」。模型没有参考像素，只能编。

**水印**：抽首帧、中段、末帧三处看。很多下载件是干净的，而用户凭印象写了整节「去水印」——这类无效指令要当面指出并删掉。

**同结构判定**：把原片主体和目标素材的部件列表各写一行，重合 ≥3 处（例：同为及膝、都有后拉链、都是厚底），即判定为「同结构替换」，必须走差异清单。

## 五、一个完整案例（可直接照抄思路）

原片：20.20s / 1440×1080（4:3）/ 30fps，鞋类特写，无任何水印，切换点 3.30 / 8.73 / 13.27 / 16.37s。

实测：单只靴子约 500–560px 高 → 属于「可要求局部细节」；但鞋底仰角只有两三帧，底面最大 200×80px → 鞋底纹路可以要求，底面文字不可以。

判定：20.2s > 15s，P0，必须先切段。切在 8.73s → 8.7s + 11.5s 两段，各自完整。

同结构比对：原鞋同为及膝、同样有后中拉链、同样是厚底 → 重合 3 处，判定「同结构替换」。原提示词只写「换成图 X」，必然只改色。改为六处差异清单后才可能改对。

无效指令：原提示词用一整节写「去水印」，实测全片无水印 → 删除。
