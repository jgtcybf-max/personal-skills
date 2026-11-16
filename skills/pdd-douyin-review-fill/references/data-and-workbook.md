# 数据结构与工作簿保留

## 辅助脚本契约

`read-xlsx` 使用 Python 标准库只读解析 XLSX，并保留每个单元格的原始类型。支持 shared strings、inline strings 和常见 sheet relationship。输出 `rows` 中每项有 `row`、`values`、`types`；列以 A、B 等命名。需人工读取真实表头后映射到下面的命名结构，不能假定所有导出都有相同列。

ID 必须是完整十进制字符串。源 Excel 若把超过 15 位的 ID 存为数值，精度可能已损失：返回后台复制或重新取得文本格式导出，不靠补零或格式转换“修复”。读取返回 `n`、科学计数法或异常位数时需检查源数据。

`requested.json` 是用户顺序的去重商品 ID 字符串数组。`pdd.json` 是每件已选择的一组规格：

```json
[
  {
    "pddGoodsId": "1020000000001",
    "pddSkuId": "1980000000001",
    "model": "DEMO-1",
    "pddSkuCode": "DEMO-1A33",
    "attributes": {"颜色": "棕色（单里5cm）", "尺码": "33"},
    "pddSpec": "棕色（单里5cm）,33"
  }
]
```

`douyin.json` 包含导出／弹窗中的候选规格，每条一 SKU：

```json
[
  {
    "douyinGoodsId": "3800000000000000001",
    "douyinSkuId": "3380000000000001",
    "model": "DEMO-1",
    "douyinSkuCode": "DEMO-1A33",
    "attributes": {"颜色": "棕色（单里5cm）", "规格": "33"},
    "douyinSpec": "{颜色:棕色（单里5cm），规格:33}",
    "douyinUrl": "https://haohuo.jinritemai.com/ecommerce/trade/detail/index.html?id=3800000000000000001&origin_type=604"
  }
]
```

示例 ID 是虚构的结构样例，不能拿来填表。`attributes` 须来自原始规格，不能为通过核验而删去不同值。脚本只把键“规格／尺码／鞋码”视为同一尺寸字段，其余键不做猜测；标准化 NFKC、空白和大小写后要求整个属性集合相等。若某平台“规格”其实含有多种含义，应在人工解析时先拆成有来源的属性，不直接套用此别名。

`match` 输出 `{requestedCount, matchedCount, verifiedRows, issues}`，有问题时退出码 2，仍保留全部报告。`verifiedRows` 可作为已核实记录数组供核验；`verify-xlsx` 也直接接受该报告，但拒绝其中仍有 `issues` 的报告。输入 ID 类型错误、重复、范围不符不会被静默纠正。编码缺失的人工匹配需自行形成相同字段的记录并保留证据。

多商品同货号／多 SKU 同编码都按歧义处理。脚本验证链接的 `id` 查询参数与商品 ID 完全一致；无法从链接可靠取得 ID 时应通过官方页面核实，不能绕开检查随便给一个链接。

`verify-xlsx` 的五个列参数依次为拼多多商品 ID、拼多多 SKU、抖音链接、抖音 SKU、平台。它在实际工作表中查找每个预期商品，要求唯一出现、五字段逐字一致、A/B/D 对应字段以字符串存储，不修改其他已有记录，也不要求示例在固定行。需要时用 `--first-row` 排除说明与表头。

## 原表写入与 native features

写入前记录原文件 hash、表头和数据布局，并在本轮内部目录备份。不要在 skill 中存用户商品清单、录屏、登录态或当次导出。

常见审核模板五列：

| 表头含义 | 写入字段 |
| --- | --- |
| 原商品goods_id | pddGoodsId |
| 原商品sku_id | pddSkuId |
| 同款goods_id／同款链接 | douyinUrl |
| 同款sku_id／sku标题 | douyinSkuId |
| 同款平台 | 抖音 |

若当前表头要求的是商品 ID 而不接受链接，遵从实际模板。原说明行“一商品一行、只需一组 SKU”是选择模式的依据，不能将本次 29 个商品或第 4–32 行写成下一次默认值。

Artifact Tool 能正确写入值，但某些导出可能改动文档属性、批注／VML 关系或文本显示。以下是已遇到并解决的问题，不代表每次都会出现：

- `format.numberFormat='@'` 后，Artifact 预览仍曾显示科学计数法。需核查导出单元格类型、effective style，并在 WPS／Excel 读取 `.Text` 与完整字符串比较。仅看 JSON `.values` 正确不足以证明显示正确。
- 原有 `docProps`、VML 命名和工作表视图曾被重写。因此保存前比较 ZIP 的原生对象、关系和数据验证；不能仅检查文件能打开。

若当前 Artifact 导出保留不完整，可将其作为**已编写并校验的值来源**，对原始包执行最小 OOXML 保留补丁：

1. 以原始 XLSX 的全部 ZIP entries 为基础，保留未涉及 parts 的原始字节；仅改目标 sheet 的选定单元格、必要 styles 及新增链接关系。
2. 保留原行、单元格样式、批注、合并、视图、下拉、关系及共享字符串。ID 使用 shared string／inline string；复制对应原样式并设文本 `numFmtId=49`，不要把所有单元格样式换成一个默认样式。
3. 对新链接添加独立、无冲突的 relationship ID，链接文字与 Target 一致。不触碰原批注／VML 的关系。
4. 保留原命名空间和兼容性声明，XML 必须可解析。可用结构化 XML 库；若做局部文本替换，分别匹配 `<c .../>` 和 `<c ...>...</c>`，避免贪婪表达式吞掉相邻单元格。
5. 比较原始与最终包：每个变更 part 都有具体原因，未授权区域值不变；再进行全部字段核对、对象核对和应用内视觉检查。

这是一条针对导出保留能力不足的恢复路径；不要绕开当前 spreadsheet skill 的 authoring 要求，也不要直接复制上次绑定固定行数／商品 ID 的脚本。

## Windows 应用验证

WPS 表格 COM 常用 ProgID `ket.Application`；读取 `Workbooks` 找确切 `FullName`，不能默认第一本一定是目标。比较所有已写入 ID 单元格 `.Value2` 与 `.Text`，应与源字符串逐字一致，检查 `.Saved`、`.ReadOnly`、`Comments.Count`、`Hyperlinks` 与 `Validation`。

`Marshal.GetActiveObject` 依赖 .NET Framework，可将 UTF-8 BOM 的 `.ps1` 交给 Windows PowerShell `powershell.exe -File` 执行；PowerShell 7 的 Marshal 可能没有这个方法。使用脚本文件可避免嵌套命令中的 `$变量` 被外层提前展开，也可避免 Windows PowerShell 将无 BOM 中文路径误解码。

COM 读取成功但窗口在后台时，可切到 WPS 检查。只关闭／重开目标工作簿，不终止整个应用。若原表未保存或 hash 已改变，检查具体变化并合并后再写入；不要直接覆盖。检查完让用户能在应用中看到已保存结果。
