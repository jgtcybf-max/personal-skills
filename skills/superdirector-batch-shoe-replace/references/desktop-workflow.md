# 桌面连接、连续提交与恢复

## 连接优先级与权限

先附着已有本机调试连接，保留用户已准备的窗口和设置。真实生成页目前含 `/micro_aigc/`；主壳 `/#/home` 与本地标题页不能用于上传。布局变化时先检查页面，不盲点，也不另开未登录网页替代桌面端。

检查进程或桌面快捷方式确定实际 exe；曾见 `D:\超级编导\超级编导.exe`，不要固定安装位置。脚本只发现名为“超级编导”的进程/快捷方式，也可显式传实际路径：

```powershell
& "<skill>/scripts/restart-app.ps1" -Mode Inspect -ExePath "<实际exe>"
```

- `attach-ready`：直接连接，不重启。
- `closed`：用 `-Mode Start` 启动。
- 无调试连接或上传恢复返回 `restart-required`：确认无无关任务/草稿受影响后，用 `-Mode Restart` 正常关闭重开。用户已授权本任务重启则继续操作，不再重复询问。
- `manual-exit-required`：正常关闭被拒绝或8秒内未退出；只此时请求用户彻底退出一次。无强杀回退。
- `open-generation-page`：应用已启动，进入 AIGC素材生产后再连接，不重新启动。

脚本只给本次启动设置 `__COMPAT_LAYER=RunAsInvoker`，并立即恢复环境，避免应用默认高权限导致无法操控。调试仅绑定 `127.0.0.1`。不修改注册表/快捷方式/系统权限。远程调试端口默认9333，冲突可传 `-Port`。Windows 错误5是权限证据，截图可读或点击没反应本身不足以判定权限。

## 持久 REPL：使用一个状态对象

使用可用的持久 Node REPL（本环境为 `mcp__node_repl__js`）。`createRequire` 加载 CJS，避免 Playwright 默认导入差异。**不要在函数内重赋顶层 `var run` 再期望外层同步；使用 `state.run` 属性，并始终从它调用。**

```javascript
var state = {}; // 只初始化一次，后续不重新赋值
state.require = (await import('node:module')).createRequire(nodeRepl.cwd + '/superdirector-session.cjs');
state.helper = state.require('<skill>/scripts/batch.cjs');
state.connection = await state.helper.connect('http://127.0.0.1:9333');
state.page = state.connection.page;
```

首次查看当前控件/定位器，避免每帧输出全页 DOM。当前 UI 线索：

| 用途 | 当前定位方式 |
| --- | --- |
| 提示词 | `[contenteditable="true"]`，不用含搜索框的裸 textbox role |
| 初次多图上传 | `input[type="file"][multiple]` |
| 缩略图及单图替换 | `[class*="_stack_item_"]` 内的单文件 input |
| 发送按钮 | `button[class*="_send_btn_"]` |
| 消息及 ID | `[class*="_message_group_"]`，`id` 属性 |
| 结果区域 | `[class*="_response_area_"]` |

必要时通过 `openBatch({selectors:{...}})` 适配新布局。不要用全局替换 `waitForFunction` 的方式修复轮询，helper 已显式设置数值轮询。

## 对话与设置

新批次通过 UI“新建对话”；恢复进入 manifest 中的 `conversationUrl`/对应标题。首次发送后 URL 才可能出现 `session_id`。标签与 message ID 都必须匹配，不把旧 ID 套到另一对话。消息未加载时先展开/滚动历史，不清除提交状态。

模型、比例、画质、张数沿用用户已选配置并记录到 `expectedSettings`，这些应是当前输入区独立可见的控件文字。曾验证 `['GPT Image2.5 精绘版','9:16','2K','1张']`，不是所有任务默认值。重启后应用曾恢复视频/Wan或极速版、16:9，因此必须核对当前输入区，不能被历史消息里的正确参数误导。

可选重命名：旧版标题编辑为 `p[class*="_op_icon_"]` 第一个，弹窗 placeholder“请输入新的对话名称”，确认按钮 accessible name 为 `confirm`。先检查当前结构，不能用旧选择器多次超时。

## 首帧与连续队列

使用 `files.py plan` 的原 manifest。prompt 只写编辑要求，helper 自动加每帧唯一批次标签。

```javascript
state.run = await state.helper.openBatch(state.page, {
  manifestPath: '<工作目录>/batch.json',
  prompt: '<依据实际鞋款编写>',
  expectedSettings: ['<模型控件文字>', '<比例>', '<画质>', '<张数>']
});
nodeRepl.write(await state.run.pump({maxSubmissions:1,budgetMs:35000}));
nodeRepl.write(await state.run.collect());
```

`collect` 返回生成中就继续按当前任务跟进；合理间隔10–20秒查看一次，不忙轮询或长时间无更新。下载首图后用本地图片工具检查，再：

```javascript
nodeRepl.write(await state.run.approveFirstFrame(1));
nodeRepl.write(await state.run.pump({maxSubmissions:4,budgetMs:35000}));
// 紧接下一轮，不等待上轮生成完成；每4–6张可收集一次。
nodeRepl.write(await state.run.collect({maxDownloads:6,downloadConcurrency:3}));
nodeRepl.write(await state.run.pump({maxSubmissions:4,budgetMs:35000}));
```

重复有界轮次直到 `all-submitted`，随后只收集。每次工具调用控制在约40秒内，以便进度反馈；不将整批包在无法观察的长循环。`maxInFlight` 默认不限，仅在应用实际有限流或并发限制时设置。所有 composer 操作串行，生成与最多3张下载并行；不要 `Promise.all` 上传多个场景。

`pump` 状态：

| 状态 | 下一步 |
| --- | --- |
| `continue` | 直接下一轮；在上传中则复用当前 handle |
| `first-frame-review` | `collect` 并查看首图，随后 `approveFirstFrame` |
| `all-submitted` | 持续收集，不能再次提交 |
| `restart-required` | 正常重启，按下文续跑 |
| `needs-attention` | 两次重启仍失败，诊断具体原因，停止自动循环 |

`stage(index)`、`submit(index)` 用于诊断或单帧操作；调用者必须检查 stage 的 `status==='staged'` 才发送。`uploading` 可继续 `stage`，不是未知草稿。`retryUpload(index)` 仅针对本批次失败且未发送的上传。正常流程由 pump 自动做一次重试。

复用首个提交消息的“使用参考图”后，helper 等参考列表恢复、仅替换图片1，并要求场景地址变化、参考图顺序不变。缩略图 `blob:` 不算上传成功。数值定时检查不受动画帧暂停影响；8秒返回可续等，30秒停滞计一次失败；重试再失败即重启。

## 重启与可靠续跑

收到 `restart-required` 后不要新建 manifest/对话，也不要改 JSON 强制设为 planned。先保留记录，正常重启：

```javascript
// 当前操作结束后释放唯一写入者；不要调用附着 browser.close()。
state.run.detach();
```

```powershell
& "<skill>/scripts/restart-app.ps1" -Mode Restart -ExePath "<实际exe>" -Port 9333
```

```javascript
state.connection = await state.helper.connect('http://127.0.0.1:9333');
state.page = state.connection.page;
// 通过 UI 返回原对话、加载已提交消息，恢复当前输入区正确设置。
state.run = await state.helper.openBatch(state.page, {manifestPath:'<工作目录>/batch.json'});
nodeRepl.write(await state.run.resumeAfterRestart());
nodeRepl.write(await state.run.pump({maxSubmissions:4,budgetMs:35000}));
```

若自动恢复了输入，先核实是否为本批次尚未发送的草稿；不要清除无关内容。`resumeAfterRestart` 要求空 composer、同一对话、已提交记录可核对，只重置没有 message ID 的帧。最多两次自动重启。单纯重连且上传仍存在时无需 `resumeAfterRestart`，直接 `stage`/`pump` 续等。

发送发生超时，先 `reconcile(index)` 查唯一标签；确认出现则沿用该任务。`uncertain` 且暂时没有消息时继续查原对话/历史，禁止盲重发。manifest 写入使用单 handle、版本检查与原子替换，外部修改时会停止，避免旧快照覆盖新消息 ID。

## 下载与验证

离屏结果可能没有 `img`，收集时先滚入视口。`gen_loading-*.gif` 不是结果。读取可见结果图的 `src`/`data-src`，只用普通下载；不调内部生成接口，不导出账户密钥。Node fetch 避免了 Electron 非ASCII user-agent 导致的 `page.request.get` 错误。

并行抓取后先保存哈希检查点，再以不覆盖方式落盘；中断后能认领哈希吻合的已下载文件。未知已有文件不会被替换。下载检查 HTTP、PNG MIME 与签名，最终用 `files.py verify` 完整解码和检查重复内容。

界面2K曾返回1152×2048或1536×2736，记录实际尺寸。只在用户要求时另做统一尺寸副本。全量验证与联系表做一次，检查首帧和可疑细节，不反复读全部输出。

## 本地回归

```powershell
node --test "<skill>/scripts/batch.test.cjs"
& "<skill>/scripts/restart-app.ps1" -Mode Inspect -ExePath "<实际exe>"
```

UI夹具只访问本机临时服务器，并启动独立无头浏览器；不会连接应用、上传用户图片或创建付费任务。测试使用已安装的 Playwright/Chromium，必要时设置 `SUPERDIRECTOR_TEST_BROWSER` 指向可执行文件。只有该测试创建的独立 browser 可关闭；实际桌面连接结束时保留应用。
