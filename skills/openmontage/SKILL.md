---
name: openmontage
description: 使用已安装的 OpenMontage 编排视频制作和现有素材剪辑，包括口播去静音、播客切片、字幕与成片渲染。用户指定 OpenMontage，或需要按其原生 pipeline 和工具注册表处理视频时使用。
---

# OpenMontage 本机入口

这是独立编写的安装适配入口，不是 OpenMontage 官方技能的副本。上游：
https://github.com/OpenMontageInc/OpenMontage （OpenMontageInc，AGPL-3.0；以上游 LICENSE 为准）。不捆绑上游代码、依赖、密钥或媒体。

## 找到安装与运行环境

读取 `~/.local/share/video-edit-runtimes/registry.json` 中的 `openmontage.root`、`openmontage.python` 与 `path_entries`。它们分别是源码目录、隔离 Python 和所需 Node/FFmpeg 工具目录。不要改用系统 Python 安装一遍依赖。缺少登记或路径失效时说明具体缺项；不要声称已经可用。

Windows 安装提供 `~/.local/bin/openmontage.cmd`。终端尚未刷新 PATH 时用绝对路径调用；该入口会配置当前子进程环境，不修改其他项目。

```powershell
& "$env:USERPROFILE/.local/bin/openmontage.cmd" doctor
& "$env:USERPROFILE/.local/bin/openmontage.cmd" list
& "$env:USERPROFILE/.local/bin/openmontage.cmd" run silence_cutter --params-file 'C:/project/silence-params.json'
```

也可用登记的 Python 执行本技能的 `scripts/run.py`。参数文件是 JSON 对象；媒体输入输出使用绝对路径。`run` 会实际执行指定工具，先读其源码确认参数。

## 开始实际制作

1. 读取源码根目录 `AGENTS.md` 和 `AGENT_GUIDE.md`；按任务选 `pipeline_defs/` 的 manifest，再读对应 `skills/pipelines/` 导演指南。不要把本入口当成完整制作流程。
2. 区分现有素材剪辑、参考片启发创作与新生成视频。对女鞋商品素材，核对货号和商品图，保留鞋头、鞋跟、落脚与鞋款一致性；不能仅按静音删除商品展示镜头。
3. 在用户项目目录保存计划、片段和输出，不覆盖原片，不把业务产物写入技能或上游源码目录。
4. 注册表入口是 `from tools.tool_registry import registry`；调用 `registry.discover()`，以 `registry.get(name)` 找工具，以 `.execute(params)` 执行，检查返回的 `.success/.data/.error`。已注册不等于已配置或可用。
5. 按实际所选工具核对模型、服务密钥和可用状态。FFmpeg 本地剪辑不需要云服务密钥；生成、转录和语音可能另需配置或模型下载。不要以安装成功代替服务验证。
6. 按上游检查点先产小样，核对时长、尺寸、音轨、关键画面及字幕，再执行本次授权范围。导出后做 ffprobe 和解码检查；涉及内容质量时另做画面/听审。

`doctor` 只检查本机登记、可执行文件和工具发现，不会调用付费服务，也不表示所有生成后端都已通过测试。
