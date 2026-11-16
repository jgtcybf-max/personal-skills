# Ego 上的抖音操作要点

本文件记录实际流程中遇到的问题；API 以本次安装版本输出的指南为准，不替代 `ego-browser skill`。

## Windows 启动

先读已安装的 `ego-browser` skill。通常位于 `~/.agents/skills/ego-browser/SKILL.md`，或 Ego 安装目录的 `ego-skills/ego-browser/SKILL.md`。

若当前进程 PATH 找不到 `ego-browser`，优先检查用户目录内的稳定版本入口：

```powershell
& "$env:USERPROFILE\.local\share\ego\active_version_dir\ego-browser.exe" skill
```

读取到 `[ego-browser:skill] end of guide` 才算完整。入口不存在则按 Ego skill 的安装说明排查，不猜测旧版本路径，不另开其他浏览器。

按照当前指南的文件写入方式保存 UTF-8 `.mjs`。Windows PowerShell 5.1 的管道和 `Set-Content` 有编码/引号问题，优先使用文件编辑工具写脚本。入口命令可保持 ASCII：

```powershell
& "$env:USERPROFILE\.local\share\ego\active_version_dir\ego-browser.exe" nodejs -e "await import('file:///C:/absolute/ascii-path/round-01.mjs')"
```

路径带中文时，将 `file:///` URL 的相应部分正确百分号编码；中文脚本内容留在 UTF-8 文件内。每轮新建完整脚本，沿用同一数字 Space ID，不重放先前已执行的操作。不要导入 Playwright 或猜测兼容接口。

## 页面检查与等待

- 用当前 `snapshot()` 中真实元素引用执行点击/输入。点击的 `label` 按当前指南提供；不要将点击专用参数传给 `fill`、`press` 或等待方法。
- `goto()` 支持 `referer`、`timeout`、`waitUntil`，此前版本不支持 `{wait:true}`；按当前指南确认。
- Douyin 导航完成后，标题、卡片与视频还可能在加载。等待与目标相关的 DOM 或视频条件，并设置有限超时，超时后查看状态再决定下一步。
- 已观察到的候选就绪条件包括标题出现且没有“视频数据加载中”，以及 `video.readyState >= 2`。它们是诊断线索，不是所有版本必有的选择器。
- `screenshot({path:绝对路径})` 后实际查看图片，不能用“截图命令成功”替代画面判断。
- 跳转播放时间后立即截图可能仍是上一帧。等待 `seeked` 或播放进度/画面准备完成，再采样。不要跳过加载/不可播放问题后仍写“已看过”。

## 抖音搜索与相关推荐

先看页面再选搜索框、按钮及“视频”筛选。曾观察到 `data-e2e="searchbar-input"` 和 `searchbar-button`，但必须以本次页面为准。

“综合”搜索的卡片有时没有普通视频链接；切到“视频”后曾可从公开 `li a[href*="/video/"]` 提取作品 URL 与卡片文本。不要等待臆造的 `search-card-video` 选择器。提取时限定公开结果区域，随后逐条打开核验。

参考作品页的相关推荐可作为搜索起点；等待它们实际渲染，去掉桌面/移动重复列表中的同一视频。作者主页也可找同风格作品，但不能只凭作者相同就入选。

上传者应从当前作品作者区域核实。标题中的 @、相关推荐作者、评论区用户都会产生 `/user/` 链接，第一个匹配不一定是上传者。

## 登录与截图故障

搜索可能出现“登录后即可搜索更多精彩视频”。按 Ego 指南 `handOff` 交还 TaskSpace，暂停该 Space 的操作，告知用户在其中登录；只在用户确认后 `takeOverTaskSpace` 并重新查看。不要操作其他账户或索要凭据。接管后空白页可检查状态并尝试一次正常刷新，再诊断原因。

Ego 窗口最小化会导致截图失败。先确认窗口状态；必要时请用户恢复并保持展开，可以切去其他应用。不要反复重试截图，也不要因此切换浏览器。

遇到访问限制或验证，按页面提示交还用户处理；无法继续时保留已核验结果并清楚说明缺口。浏览器交还、接管与结束的准确调用均服从本次运行指南。
