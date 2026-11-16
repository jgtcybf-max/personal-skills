# 权限和坐标输入助手

仅在普通 Windows MCP 输入未生效、且确认目标超级编导以管理员权限运行等需要时读取。本工具是可选输入通道，不是上传 API。用户对本次素材上传的授权仍适用；UAC 系统授权由用户亲手处理。是否恢复/重开超级编导遵从当前用户授权；已有授权时先核保存及在途任务后执行，不反复请求同一许可。始终不更改系统权限或UAC。

## 开始和停止

在以下示例中，先用任务变量指定实际路径。普通运行优先；需要管理员输入时省略 `-NoElevate`，提前告知用户可能有 UAC 弹窗。`Start` 启动隐藏 PowerShell，输出 `controlDir`，每次新建随机目录。默认运行20分钟，当前`LifetimeMinutes`支持1—60分钟；任务结束调用`Stop`。`Start`与`status`返回`expires_at_utc`及`remaining_seconds`，`ready.json`记录生命周期快照；实时剩余寿命以`status`或到期时间重算。探针`Probe`没有助手生命周期，相关值为null。不自动延长或无限续开。

```powershell
$inputScript='<skill>\scripts\desktop-input.ps1'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $inputScript -Mode Probe
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $inputScript -Mode Start -NoElevate
# 记录上一步输出的 controlDir，作为 $taskControl。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $inputScript -Mode Send -ControlDir $taskControl -Request '<任务目录>\input-request.json'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $inputScript -Mode Stop -ControlDir $taskControl
```

`Probe` 不移动鼠标、不按键，返回 DPI 模式、管理员状态、鼠标和屏幕边界。助手必须返回 `physicalPixels:true`；失败则不发鼠标输入。普通模式的协议验证使用 `status`，不需要系统授权。manifest声明`highestAvailable`、无法读取进程令牌或权限访问被拒，均不能单独证明目标实际以管理员身份运行；记录已知事实与推断，核现有可用信息后选择输入通道。

## 请求文件

UTF-8 JSON；`Send` 生成请求 ID 并等待匹配结果。可用动作：

| action | 字段 | 含义 |
| --- | --- | --- |
| `status` | 可选 `echo` | 无桌面输入，检查状态及中文 UTF-8 往返 |
| `focus` | `handle` | 尝试恢复最小化窗口并聚焦，返回实际 `foregroundHandle` / `focused`；不能沿用历史句柄 |
| `nativeFields` | `handle,processId` | 回读指定顶层窗口内最多8个原生Edit字段，返回字段句柄及文本；不读密码框 |
| `nativeText` | `handle,processId,fieldHandle`，及 `text` 或 `textFile` | 写入明确指定的原生Edit并逐字回读；不发送确认键 |
| `click` | `x,y`，可选 `button:"right"`、`count:2` | 物理像素点击 |
| `wheel` | `x,y,delta` | 滚轮，120 是一个常用档位，不能据此推断画布必定缩放 |
| `keys` | `keys` | WinForms SendKeys 格式，如 `{ENTER}`、`{ESC}`、`^a` |
| `text` | `text` 或 `textFile` | 设置剪贴板并粘贴；`textFile` 可直接用 materials.py 的选择文件 |
| `drag` | `x1,y1,x2,y2` | 拖动；先核实选择/平移模式和节点位置 |
| `screenshot` | `path`，可选 `region:{x,y,width,height},maxWidth` | 直接捕获真实物理桌面并在助手内缩图；PNG父目录须已存在，返回原点/尺寸/缩放系数/前台句柄 |
| `clipboardRead` | 无 | 仅在本任务刚复制字段后读取文本全文，UTF-8 JSON返回，最多32767字符 |
| `stop` | 无 | 停止助手 |

例：`{"action":"text","textFile":"C:\\工作\\upload-manifest-selection-image-01.txt"}`。

不要在共享剪贴板里保存敏感信息；这里只粘贴本次选择的文件路径。一个助手同时只允许一个调用者。`ok:true` 仅说明输入动作已执行；切换窗口后重新核前台窗口/焦点、截图原始尺寸和原点，先一次无付费可见操作验证，避免文字进入Codex草稿。`nativeText` 的 `verified:true` 进一步证明该字段的即时回读一致，仍不代表选中正确文件或上传完成。超时先看屏幕，不盲重发动作。

## 常驻Node客户端

`scripts/desktop-client.mjs`直接通过同一个controlDir发送JSON，不为每步新建PowerShell。它不启动、提权或延长助手。先按前文Start取得当前controlDir，然后在持久Node会话导入：

```js
var { createDesktopClient } = await import('file:///C:/Users/TTT/.codex/skills/superdirector-canvas-upload/scripts/desktop-client.mjs');
var canvasInput = createDesktopClient(currentControlDir);
var state = await canvasInput.send({ action: 'status' });
// 输入坐标始终为物理像素；expectedForegroundHandle须来自当前观察。
var shot = await canvasInput.send({ action: 'screenshot', path: absolutePng, maxWidth: 1920 });
// 本任务刚执行Ctrl+C后读取，再与本地定稿比较。
var copied = await canvasInput.send({ action: 'clipboardRead' });
// 已观察且稳定的非付费字段操作，也可用sequence(items,{observedStable:true})，最多6步。
// 完成后send({action:'stop'})，再close()释放本客户端；close本身不会停止助手。
```

输入可带 `expectedForegroundHandle`；前台不同即拒绝，不点击。稳定且已观察的非付费动作可在单次工具调用顺序await，不并发操控，不能跨未知菜单或把付费生成放进组合操作。底栏核对、生成点击和受理确认仍分开。超时/错误后先看桌面和原任务，再按客户端恢复接口解除停发；不自动重试。

超时或助手错误后，客户端停止后续命令，避免覆盖在途请求。用现有只读桌面工具观察；`readPendingReceipt()`等到确切同ID回执，再由操作者`acknowledgeObserved(requestId)`解除停发。未有匹配回执不能解除或新建客户端绕过。`readReady()`仍可检查到期。模块不会自动重发付费或任何输入。

## 原生文件框的有反馈输入

在本来就需要上传时，先取得**当前文件选择框**的顶层句柄和PID，不能拿超级编导主窗口句柄代替弹窗。请求 `{"action":"nativeFields","handle":123456,"processId":1234}`，结合界面确认返回的哪个Edit是“文件名”；不按数组序号猜测，`limitReached:true` 表示最多只列出8项。

然后请求 `{"action":"nativeText","handle":123456,"processId":1234,"fieldHandle":234567,"textFile":"C:\\任务\\selection-short.txt"}`。使用短名称前必须确认当前目录与本批 `directory` 一致。写入成功返回 `verified:true`、实际文本和 `confirmationSent:false`，再单独确认“打开”按钮；这个动作不会自己上传。

仅支持原生 `Edit` / WinForms Edit，不适用于Electron页面里的普通输入区、提示词框或画布。校验当前PID、顶层/父子关系、类型，拒绝密码、只读、失效字段、空值、NUL和超32767字符文本；每条Win32消息超时250毫秒。没有可识别字段、权限阻止或回读不一致时，观察界面后回到原 `text` 粘贴方式，不盲重试。

2026-11-14隐藏自建控件测试：15个协议用例通过；中文文本和文件内容写入回读约0.36—0.39秒（含独立Send进程启动）。这是本地测试，真实超级编导文件框、管理员输入、最小化恢复和挂死窗口超时尚未验证。不能据此承诺上传总耗时或提速比例。

## 坐标换算

读取当时截图的原始尺寸、返回缩放比例和裁剪区域起点。将图中坐标换算为完整虚拟桌面**物理像素**再传 `x,y`。例：全屏截图 3840×2160 缩到 1920×1080，返回图的 `(300,200)` 对应物理 `(600,400)`；裁剪图还要加区域左上角偏移。

新助手设置每显示器 DPI awareness，**不要再额外除以 Windows 150% 缩放倍率**。本次旧助手曾需要除以 1.5 的补偿只适用于旧实现。每次开始用状态或安全的空白点验证映射，不直接点生成/删除等动作。
