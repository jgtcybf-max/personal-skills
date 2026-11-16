# 筛选数据与文档导出

在本次任务的工作目录保存 UTF-8 `selection.json`。以下结构沿用已经完成过的分类清单；示例占位值用于说明字段，必须替换成浏览器实际核验的数据，不能直接当成推荐。

```json
{
  "title": "抖音相似风格视频清单",
  "date": "YYYY-MM-DD",
  "intro": "说明筛选范围、实际数量与限制。",
  "minLikes": 1000,
  "targetPerCategory": 10,
  "excludedIds": [],
  "categories": [
    {
      "name": "按本次参考命名的类别",
      "reference": "原始参考作者与标题",
      "referenceUrl": "https://v.douyin.com/实际短链/",
      "referenceCanonical": "https://www.douyin.com/video/实际参考视频ID",
      "focus": "画面风格与筛选重点",
      "items": [
        {
          "key": "A1",
          "id": "实际候选视频ID",
          "author": "实际上传者",
          "title": "作品页实际标题",
          "duration": "可选，实际片长",
          "similarity": "基于画面核验的具体相似点及重要差异",
          "styleDimensions": ["实际相同的核心主体或鞋款", "实际相同的构图或拍法"],
          "likes": 12000,
          "likesDisplay": "1.2万",
          "likesCheckedAt": "YYYY-MM-DD HH:mm 时区",
          "likesEvidence": "当前作品页点赞图标旁显示1.2万；对应截图路径或公开DOM观察位置",
          "match": "可选，接近程度与差异摘要"
        }
      ]
    }
  ]
}
```

- `categories`、分类名称和每条 `id`、`author`、`title`、`similarity`、`styleDimensions`、`likes`、`likesDisplay`、`likesCheckedAt`、`likesEvidence` 必填。视频 ID 保持字符串，避免大整数精度丢失。
- `minLikes` 默认 1000，`targetPerCategory` 默认 10；只有用户明确改动要求时才覆盖。`excludedIds` 是用户已否定作品的 ID 数组，本轮推荐不得重用其中任何作品。
- `styleDimensions` 至少两个非空的实际匹配维度，并在 `similarity` 中解释画面证据。格式校验不代表风格真实通过，核心风格偏离的候选不得放入 `items`。
- `likesDisplay` 保留点赞区域数值，例如 `1234`、`1.2万`；可用千/万/亿、k/w 和逗号分隔。`likes` 为对应显示值换算后的整数，必须达到 `minLikes`；平台以万等单位显示时，换算值不是精确计数，文档须注明。不得拿猜测数、其他互动指标或作者总获赞填充。模糊值、隐藏值、`1000+` 等无法核实数值的显示须重新核验，不猜值。
- `likesCheckedAt` 记录本次实际查看时间（建议带时区），`likesEvidence` 说明是当前作品点赞区域以及证据路径/位置；仅搜索卡片不足以完成最终核验。
- 默认候选 URL 为 `https://www.douyin.com/video/{id}`。只有在浏览器实际打开该 canonical 地址后才能入选；拼接公式本身不能证明链接真实存在。
- 原始参考与新增推荐分别保存。`referenceCanonical` 取实际跳转地址；无法核实时可以留空并在参考说明中明确“未核验”。不要猜测 ID。
- 图片参考使用 `reference` 描述图片内容，`referenceUrl` 与 `referenceCanonical` 可空；来源保存在工作笔记，不猜测原视频或作者。原始视频链接未能核验时，在 `reference` 中注明状态，避免与无链接的图片参考混淆。
- 一个分类可围绕一条参考构建；多个同风格参考用以下 `references` 数组替代分类中的三个单条字段。不要把合并参考算进新增视频数量。
- 可额外保存 `checkedAt`、`evidencePath`、`visualNotes` 等复查元数据；文档未必展示它们，截图和核验备注应保留在工作目录。
- 待核验候选不写入 `items`。另存工作笔记，交付时说明限制；导出脚本验证数据结构与链接一致性，不能代替浏览器中的画面核验。

多参考字段示例（放在对应分类对象内）：

```json
"references": [
  {"reference": "第一条原始参考的作者与标题", "referenceUrl": "实际分享链接", "referenceCanonical": "实际canonical链接"},
  {"reference": "用户提供的第二张参考图：夜景双人全身构图", "referenceUrl": "", "referenceCanonical": ""}
]
```

## 运行

需要 Python 3 和 `python-docx`。优先使用已有文档运行环境；若普通 `python` 缺依赖，查当前 `documents` skill/工作区依赖提供的环境，不假设所有 Python 都装有 `docx`。

```text
python <skill目录>/scripts/export_document.py --input <selection.json绝对路径> --validate-only
python <skill目录>/scripts/export_document.py --input <selection.json绝对路径> --output <清单.docx绝对路径> --markdown <清单.md绝对路径>
```

导出器拒绝低于门槛、未知点赞、点赞显示与整数不一致、缺点赞证据、重复候选 ID、已排除作品、原始参考混入推荐、缺失核心字段和与 ID 不一致的候选 URL。每类不足 `targetPerCategory` 时可导出，但报告与文档会显示数量缺口；不能把不足十条的文档描述为完成每类十条。分类可自然跨页，不强行压入一页。导出后仍须核对实际数量、原参考区分、可点击超链接，并渲染 Word 逐页查看。脚本输出不能作为内容真实或风格相似的证明。

Word 采用 Letter 纵向页面与 11 磅正文，按分类分节，每条显示作者、作品标题、具体相似点与差异、页面点赞值、核验时间和可点击链接。完整 `styleDimensions` 与 `likesEvidence` 保存在 JSON，Markdown 也保留审计信息；Word 中的证据位置简写为“详情页点赞区”，避免本地截图路径干扰阅读。
