# 数据入口和故障处理

本机设置在技能根目录 `config.json`，不含凭据。默认本人微信账号为 `D:\xwechat_files\wxid_YOUR_ACCOUNT`，Codex根目录为 `C:\Users\TTT\.codex`。路径更换时只调整对应字段，不能扫描别人的账号来补数据。

## 运行与输出

`scripts/collect.py` 默认最近7个自然日。`--date today`、`--date yesterday`、`--days 7` 或 `--start YYYY-MM-DD --end YYYY-MM-DD` 指定区间，开始含、结束日含；今天截至采集时刻。`--output`只接受新目录或空目录。

输出在工作区 `outputs/daily-work-review/<运行时间_随机后缀>/`：

- `coverage.json`：源状态、覆盖时段、发送者复核、遗漏和计数。`semantic_report_generated:false` 表示只是采集完成。
- `private/wechat.jsonl`：脱敏消息，含本人标记、原数据库/表/local_id等定位。
- `private/codex_events.jsonl`：脱敏目标、助手陈述、工具调用/输出，含源日志行号和call_id。
- `private/codex_threads.json`：脱敏会话元信息，不把会话数当工作数。
- `简报.md`与`private/evidence.json`由使用技能的Agent阅读证据后生成；完成后将coverage的semantic_report_generated改为true并写report_path。没有证据就说明缺失。

分页读取示例：

```powershell
python 'C:\Users\TTT\.codex\skills\daily-work-review\scripts\read_evidence.py' --run '<运行目录>' --source wechat --day 2026-11-13 --limit 120
python 'C:\Users\TTT\.codex\skills\daily-work-review\scripts\read_evidence.py' --run '<运行目录>' --source codex --day 2026-11-13 --limit 100
```

继续读`next_offset`对应页。`--chat`/`--thread`可看同一任务的后续；不能只读本人而漏掉对方完成反馈。工作线程里当前复盘自身的采集操作可简记为复盘，不把它的上千次工具调用变成上千件业务工作。

## 微信

支持本机已经验证过的微信4.1 Config.Cipher/WCDB格式。自动用进程父子关系识别唯一主Weixin进程，只以 `PROCESS_VM_READ | PROCESS_QUERY_INFORMATION` 读取；不存在主进程、权限不足、格式不兼容或数据库页校验失败就返回unavailable，不自动重启、注入、写进程或回退调试器。

从原.db与WAL读取前后稳定状态；校验WAL校验和及提交边界、数据库页HMAC；只在内存中解密并用SQLite查询。每个分片独立Name2Id映射，按服务器ID去重，FTS以原文字摘要、会话和时间做独立发送者复核，不用经过脱敏的文本去模糊匹配。匹配为0不表示已验证，disagree>0时暂停本人归属结论。

Python需3.12、64位；cryptography/zstandard等依赖已经包含在`scripts/_deps`，来自本机此前实际运行版本。若默认python换成其他ABI，用现有Python3.12运行，不下载不明可执行程序。

微信没运行可让用户登录；同一会话已授权的只读分析不重复问权限。若使用已有脱敏摘录，显式传`--wechat-cache '<消息jsonl>'`，输出标为cached，并在报告说明实际记录截止时间；不能称读到了新微信。旧的导出自动日报目录`D:\微信聊天记录`可能为空，不要把那套等待页当作本助手的数据。不要读历史keys.json或落盘明文库补失败。

## Codex

只读`state_5.sqlite`（mode=ro，保留WAL可见），按会话路径读取相关JSONL。排除子代理和注入环境，只按范围内实际事件归日。旧会话今天的活动仍要读。工具call_id用于对齐执行结果；工具结果摘录有长度限制，需要关键完整证据时按源行读，不将整份日志全部展开。

`user_request`是任务；`assistant_report`是AI陈述；`tool_call`不代表调用成功；`tool_result`需判断内容中的返回状态。`automation_*`不代表用户当天新下的指令。多个镜像用户事件/任务完成消息已去重。数据库不可用时coverage会注明，不能仅凭聊天title猜测活动。

## 保留边界

只在本地写脱敏摘录和报告，不上传聊天、不发送微信、不改原数据。不落盘密钥、原始进程内存或明文数据库。brief保留必要事实，不贴配置代码、账号、财务账户、订单明细。若旧清理曾遭自动审批拒绝，不通过另一工具绕过删除；本流程不依赖那些文件。
