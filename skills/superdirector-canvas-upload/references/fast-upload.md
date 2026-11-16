# 快速上传：准备一次、只传缺项、每批一次核验

上传skill优化只更新本地流程与工具，不在真实画布重复上传作为测试。用户已要求上传时才进入真实桌面。定位、工具发送、UI等待、网络上传分别计时；不能用发送延迟替代整批上传耗时。

## 清单和缺项队列

首次用materials.py，或直接复用prepare_run的upload-manifest.json。文件选择先视频再图片，同类型同父目录默认每批5项；该值是当前保守策略，不是平台硬上限。不要为了少一次文件框擅自把9张一批。

已有确切清单后，`upload_queue.py`只检查指定文件，不解码/抽帧，不遍历其他商品目录。收据绑定本次清单、画布和独立任务组身份，不能把同画布旧成功组或别的画布同名素材当已上传。新来源须在新空白区上传独立副本；只对同组续跑去重。其状态仅用于安排后续操作，不读超级编导内部数据。

```powershell
python -X utf8 "<skill>/scripts/upload_queue.py" plan --manifest "<任务>/upload-manifest.json" --state "<任务>/upload-state.json" --canvas "小蒋无限画布" --task-key "来源ID-货号颜色-独立组01" --out "<任务>/upload-queue"
```

读取输出queue.md/plan.json，仅执行pending批次。verified须来自操作者实际UI证据；unknown留在hold，先查原节点，不重新提交。核对现有节点也可直接标记verified，无需再上传一次。文件签名只比路径、字节和修改时间，不能检测刻意保留这些值的内容替换；确知内容变动需重新核，不把它当内容SHA256。

```powershell
python -X utf8 "<skill>/scripts/upload_queue.py" mark --manifest "<任务>/upload-manifest.json" --state "<任务>/upload-state.json" --canvas "小蒋无限画布" --task-key "来源ID-货号颜色-独立组01" --file "C:/确切素材.jpg" --status verified --evidence "本批节点截图路径及核对说明" --node-id "实际节点ID"
```

单执行端维护收据，canvas/task-key不匹配或旧版无作用域收据直接拒绝；新独立组必须新state，不能借旧组verified跳过上传。每批完成后一次调用内依次标记确切文件，再刷新plan；不每张一个模型往返。缺失只对该文件回pending，受理未知标unknown；unknown即使本地文件变化也继续hold，先查原UI。最终交付仍独立核全清单与云端保存。参数和输出细节以`--help`为准。

## 文件框：绝对路径一次写入

确认本次弹窗为原生Open文件选择框，取得当前顶层handle、processId及文件名Edit的fieldHandle。不要用主窗口句柄或猜Edit序号。句柄只在此弹窗存活期间有效。

在已有时限助手和desktop-client的持久Node会话中：

```js
var { fillUploadBatch } = await import('file:///C:/Users/TTT/.codex/skills/superdirector-canvas-upload/scripts/upload-dialog.mjs');
var filled = await fillUploadBatch(canvasInput, {
  batch: nextBatch, handle: dialogHandle, processId: dialogPid, fieldHandle: filenameEdit
});
// filled.verified只证明文件名字段回读；confirmationSent为false。
// 核本次批次及回读后，单独确认“打开”，观察上传结果，不自动标上传完成。
```

该函数使用原生字段消息，不切目录、不碰剪贴板，中文/空格/#/°均作为字符串传递。批次文件及selection_file不一致直接拒绝。原生Edit不支持时，用同一已观察输入框的粘贴和clipboardRead回读；只选一种已验证通道，不反复探索。

## 每批观察边界

- 首次入口菜单各观察一次；已观察稳定的非付费操作放一次调用中顺序执行，未知子菜单或弹窗出现即观察。
- 文件框填写与全文回读可一次完成；“打开”单独确认并观察，不把回读成功当上传成功。
- 上传期间看实际状态，完成即核，不固定等30秒。批次的文件名/缩略图集中读取；异常才展开单图。顶部最终保存要有独立证据。
- 不新建生成节点、不点生成。排版只移动本次新节点，按既有左列图/左下视频规范一次放置。旧成功组素材节点不直接复用或增删连线；新任务新区上传本地原图/确证无副作用的独立副本。同一新任务组已上传的节点才可续用。
- 拍证据用助手直接缩图/局部截图，减少CLI+Python进程；全屏用于焦点或视野变化，不能裁掉需要核实的菜单/参数。

## 验证和速度边界

验证覆盖清单、差量计划、未知状态停传、文件变化、原生Edit写入回读；控件fixture不代表超级编导真实上传全链通过。网络传输和平台处理时间不能由本地脚本保证缩短。真实业务下一次按相同视频/图片数量记录文件框次数、工具调用数、UI/网络等待、开始到全部核验完成时间，再比较。
