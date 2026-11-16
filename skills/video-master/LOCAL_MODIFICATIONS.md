# 本机修改说明

修改日期：2026-11-16。上游：AI 创意研究室，ai-creative-coder/video-master，commit a6aab97904340dffe14461cd77a89aa8256b0c53。原始许可证 AGPL-3.0-only，LICENSE 与 NOTICE 保持原样。本文件与修改后的配套源代码随技能保存。

- 添加 Windows 本机 runtime 配置与媒体定位 helper，复用现有 Python、FFmpeg、FFprobe。
- 媒体解码/切镜失败明确报错，避免将失败误当作没有切镜或音频候选。
- 尾帧附近抽帧返回成功但无图片时，回退至可用末帧，并在索引记录请求/实际时间；无图片明确报错，避免使用旧文件。
- 禁用另启 Edge/Chrome 的 PDF 路径，遵守用户真实 Ego 要求；HTML、PNG 功能保留。
- 已明确模式不重复询问；安装本身不要求模式选择。说明与既有 rea-video、女鞋商品替换流程的任务边界。
- Pillow 最低版本调整为10.1，以支持脚本实际使用的字体 size 参数；本机验证版本12.3.0。

这份安装版不更改上游作者，不声称生成视频效果已实测。原始版本保存在本任务的 source/video-master 检出目录。
