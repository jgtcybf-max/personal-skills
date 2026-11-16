---
name: douyin-product-image-export
description: Download all main carousel and detail-page images from Douyin Mall or Jinritemai product links, preserving original resolution, page order, and complete long images. Export a source list, main-image contact sheet, and ZIP. Use for 抖音商城商品图片下载、全部主图和详情图导出 or copied product share messages.
---

# 抖音商品图片完整导出

将用户提供的抖音商城商品链接整理成可核对的本地图片素材包。商品名、商品ID、图片内容与顺序以实际商品页为依据。

## 读取完整商品页

1. 提取分享短链，使用当前可用的 Playwright MCP 或浏览器能力打开，核对实际商品ID和名称；不只下载分享链接中的封面。
2. 读取轮播全部图片，滚动商品详情容器到底部；如出现“展开详情”等控件，展开后继续滚动。等待详情图片完成加载，确认已无新增图片。
3. 保存商品接口响应和页面图片清单。实际接口结构、滚动容器及捕获代码见 [references/browser-capture.md](references/browser-capture.md)。优先用商品接口的有序数组，并与页面DOM逐项核对；不能将网络请求到达顺序当成页面顺序。
4. 只提取本商品轮播和详情区域的图片，排除推荐商品、店铺头像、图标。同一商品详情中的品牌故事、包装说明属于详情内容，不能因出现其它鞋款而误删。

## 下载与交付

使用 `scripts/export_product_images.py`。依赖 Python 和 Pillow；浏览器由当前会话操作，脚本不依赖某台电脑的浏览器安装路径。

```powershell
python "$env:USERPROFILE\.codex\skills\douyin-product-image-export\scripts\export_product_images.py" `
  --h5-response "capture\h5.json" `
  --detail-response "capture\detail.json" `
  --dom-images "capture\dom.json" `
  --share-url "用户提供的抖音商品链接" `
  --output "$env:USERPROFILE\Desktop\品牌_货号"
```

- 用户指定保存路径时使用该路径；未指定时，默认桌面 `品牌_货号`，不能核实名称时用 `抖音商品_实际商品ID`。
- API不可读取但完整页面可读取时，可省略两个响应参数，使用完整DOM清单，并补充 `--product-name`、`--product-id`。DOM字段见参考文件。
- 以原资源URI去除同一类别内不同CDN、不同缩略尺寸造成的重复，保留首次出现的页面位置及映射。主图和详情分别编号；不跨类别删除页面确实存在的图片。
- 优先取得原分辨率版本，核对资源声明宽高和实际解码宽高。长图完整保存，不拼接网页截图、不裁切、不拉伸、不本地重新压缩。扩展名以实际解码格式为准，CDN返回PNG时保存为PNG。
- 原图获取失败时记入清单，不能用1080px轮播缩略图冒充1200px原图；无法验证原始尺寸时明确标记。
- 输出目录非空时脚本递增目录名称，压缩包同名时递增文件名，使用脚本返回的实际路径。保留用户已有文件。

默认输出：

```text
品牌_货号/
  main_images/main_01.png ...
  detail_images/detail_01.png ...
  来源清单.txt
  主图预览联系表.png
  manifest.json
  errors.json
品牌_货号.zip
```

`来源清单.txt` 包含名称、分享链接、实际商品ID、页面位置数、去重后下载数、逐图地址/尺寸/哈希、重复位置映射，以及下载失败或无法核实的项目。ZIP包含本次成果，脚本校验成员哈希；最终校验结论写入ZIP旁的 `*_验证结果.json`，并在命令输出中返回。

脚本非零退出或完整性核对失败时，检查原因；可刷新已失效的链接或使用同一资源备用CDN重试。需要登录或页面无法读取时，说明实际获得的数量与缺失范围，不宣称“全部下载成功”。

## 最后检查

核对主图/详情数量与页面证据，全部文件可解码、长图尺寸完整、名称和格式正确。查看主图联系表，确认没有推荐图或图标混入。给出实际文件夹、ZIP、成功数量、失败清单及去重说明，并用绝对路径展示联系表。

已有 `scripts/download_from_network_log.py` 保留兼容旧调用，可用来导出已捕获的图片。它不能证明页面已展开完整，也不保证下载的是原分辨率；完整原图导出应使用上述新流程。

