# 商品页捕获与原图来源

使用当前会话实际提供的浏览器工具，按其参数定义操作；不必为已可使用的Playwright MCP额外安装Node或另起浏览器。

## 页面与接口

短链通常跳转到 `haohuo.jinritemai.com/ecommerce/trade/detail/index.html`，实际商品ID位于 `id` 参数。以页面/商品响应的ID核对用户商品，不能从短链字符串推算。

从本次页面网络请求中定位并保存JSON响应，索引每次以实际请求列表为准：

| 响应 | 需要的字段 |
| --- | --- |
| `/aweme/v2/shop/promotion/pack/h5/` | `promotion_h5.basic_info_data.product_id`、`title_info.title`；`promotion_h5.head_figure_data.media_list` 中 `type=image` 的 `content_list[].url` |
| `/aweme/v2/shop/promotion/pack/detail/` | `detail_info.detail_imgs_new[].image`，或 `detail_info.detail_imgs[]`；图片的 `uri`、`url_list`、`width`、`height` |

例如使用 `browser_network_requests` 定位响应，再使用 `browser_network_request(part="response-body", filename=...)` 保存。工具只允许写浏览器输出目录时，先保存到该目录，再将文件复制到工作区的本次捕获目录。接口可能有动态签名，优先使用浏览器成功取得的响应，不臆造签名或重放其它商品请求。

## 完整加载与DOM清单

先观察页面实际结构。下列选择器适用于已验证的商城H5版本，改版后应适配实际DOM，不能用空选择结果证明没有图片：

- 滚动容器：`.detail-container__body`（不是始终滚动 `window`）。
- 主图：`.head-figure__media-view__content`，图片在 `style.backgroundImage`，DOM顺序是轮播顺序。
- 详情：`.product-big-img-list__every-img`，图片在 `currentSrc` 或 `src`，DOM顺序是详情顺序。

展开实际可见的详情展开控件后，分段滚动该容器，间隔约100—250ms供懒加载触发；到达底部后再核对高度、图片数是否稳定以及所有详情图片是否完成加载。内容仍增加时继续；遇到加载失败则记录，不无限重试。参数弹窗、价格说明、销量说明和协议不等同于“展开详情图片”。

保存以下结构的JSON为 `dom.json`。这是输入格式示意，实际值必须由页面提取：

```json
{
  "productId": "页面实际商品ID",
  "title": "页面实际商品名称",
  "atBottom": true,
  "carousel": ["第1张轮播完整URL", "第2张轮播完整URL"],
  "details": [
    {"url": "第1个详情图片URL", "width": 790, "height": 1459, "loaded": true}
  ]
}
```

确认已到底部后，可用 `browser_evaluate` 提取并通过其 `filename` 参数保存：

```javascript
() => {
  const scroller = document.querySelector('.detail-container__body');
  const main = [...document.querySelectorAll('.head-figure__media-view__content')];
  const detail = [...document.querySelectorAll('.product-big-img-list__every-img')];
  const title = document.querySelector('.title-info')?.innerText.trim() || '';
  if (!scroller || !main.length || !detail.length) throw new Error('需要检查实际页面结构');
  return {
    productId: new URL(location.href).searchParams.get('id'),
    title,
    atBottom: scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 4,
    carousel: main.map(x => x.style.backgroundImage.match(/url\(["']?(.*?)["']?\)/)?.[1]).filter(Boolean),
    details: detail.map(x => ({url: x.currentSrc || x.src, width: x.naturalWidth,
      height: x.naturalHeight, loaded: x.complete && x.naturalWidth > 0}))
  };
}
```

API与DOM数组的长度及逐项资源ID应一致，包括页面重复展示的位置。若DOM虚拟化或有新分页，只能在理解该页面机制后建立同等完整的清单，不能丢弃不匹配项来让校验通过。

## 原图与去重

商品资源通常形如：

```text
https://p3-item.ecombdimg.com/img/ecom-shop-material/jpeg_m_HASH_sx_SIZE_www1200-1200~tplv-5mmsx3fupr-resize_q:1080:1080:q90.webp
```

资源URI为 `/img/` 之后、`~` 之前部分。相同URI的p3/p26地址或不同尺寸变换仍是同一图片。`_www1200-1200` 表示源资源声明尺寸；详情也可能声明790×1459等非正方形尺寸。

验证过的原分辨率候选：

```text
https://p26-item.ecombdimg.com/img/资源URI~tplv-5mmsx3fupr-image.png
https://p3-item.ecombdimg.com/img/资源URI~tplv-5mmsx3fupr-image.png
```

这是CDN提供的原分辨率PNG版本，不保证与商家上传文件的二进制格式相同。直接保留HTTP响应字节，按解码格式命名；没有必要将PNG再转JPEG。去掉整个 `~` 后缀的裸地址可能返回400，不能假定它才是可下载原图。

对未知CDN，先检查页面是否提供明确的原图地址。未验证的变换规则或仅有缩略图时，报告限制；不要承诺不存在的原始分辨率或自行放大。

## 交付验证

脚本负责尺寸/解码、顺序/去重映射、来源清单和ZIP校验；另需实际查看主图联系表。详情中同一图片连续展示两次时，记录原页面的两个位置，保留首次位置，不把去重后的数量差异报成下载失败。
