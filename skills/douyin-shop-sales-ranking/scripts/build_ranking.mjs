import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const artifactEntry = require.resolve("@oai/artifact-tool");
const { SpreadsheetFile, Workbook } = await import(pathToFileURL(artifactEntry).href);
const sharp = require("sharp");

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  throw new Error("Usage: node build_ranking.mjs <input.json> <output.xlsx>");
}

const input = JSON.parse(await fs.readFile(inputPath, "utf8"));
if (!Array.isArray(input.products) || input.products.length === 0) {
  throw new Error("input.products must be a non-empty array");
}

const allowedBases = new Set(["exact_7d", "estimated_7d", "snapshot_delta", "snapshot_pending", "unavailable"]);
if (!allowedBases.has(input.sales_basis)) {
  throw new Error(`Unsupported sales_basis: ${input.sales_basis}`);
}

const seen = new Set();
const normalized = input.products.map((product, index) => {
  const productId = product.product_id == null ? "" : String(product.product_id);
  const promotionId = product.promotion_id == null ? "" : String(product.promotion_id);
  const stableKey = promotionId ? `promotion:${promotionId}` : productId ? `product:${productId}` : `row:${index}`;
  if (seen.has(stableKey)) throw new Error(`Duplicate stable product key: ${stableKey}`);
  seen.add(stableKey);
  return {
    ...product,
    product_id: productId,
    promotion_id: promotionId,
    source_order: Number.isFinite(product.source_order) ? product.source_order : index + 1,
    price: Number.isFinite(product.price) ? product.price : null,
    sales_7d: Number.isFinite(product.sales_7d) ? product.sales_7d : null,
    current_cumulative_sales: Number.isFinite(product.current_cumulative_sales) ? product.current_cumulative_sales : null,
    followup_cumulative_sales: Number.isFinite(product.followup_cumulative_sales) ? product.followup_cumulative_sales : null,
  };
});

const salesValue = (product) => {
  if (product.sales_7d != null) return product.sales_7d;
  if (product.current_cumulative_sales == null || product.followup_cumulative_sales == null) return null;
  const difference = product.followup_cumulative_sales - product.current_cumulative_sales;
  return difference >= 0 ? difference : null;
};
const hasRankableSales = normalized.some((product) => salesValue(product) != null);
const products = hasRankableSales
  ? [...normalized].sort((left, right) => {
      const leftSales = salesValue(left);
      const rightSales = salesValue(right);
      if (leftSales == null && rightSales == null) return left.source_order - right.source_order;
      if (leftSales == null) return 1;
      if (rightSales == null) return -1;
      return rightSales - leftSales || left.source_order - right.source_order;
    })
  : [...normalized].sort((left, right) => left.source_order - right.source_order);

const workbook = Workbook.create();
const ranking = workbook.worksheets.add("商品排行");
const methodology = workbook.worksheets.add("口径说明");
const startRow = 6;
const endRow = startRow + products.length - 1;
const scopeLabels = { full_shop: "全店商品", live_cart: "当前直播购物车", showcase: "达人橱窗", related: "相关商品" };
const basisLabels = {
  exact_7d: "精确7天销量",
  estimated_7d: "平台估算7天销量",
  snapshot_delta: "累计销量快照差值",
  snapshot_pending: "等待第二次累计销量快照",
  unavailable: "公开端无有效7天销量",
};
const period = input.period_start && input.period_end ? `${input.period_start} 至 ${input.period_end}` : "未提供历史周期";
const title = hasRankableSales ? `${input.shop_name || "抖音店铺"}｜商品7天销量排行` : `${input.shop_name || "抖音店铺"}｜商品公开数据快照`;
const warning = hasRankableSales
  ? `销量口径：${basisLabels[input.sales_basis]}；统计周期：${period}。`
  : `当前不能生成历史7天销量榜：${basisLabels[input.sales_basis]}。空白不代表0，不按未知销量排序。`;

ranking.mergeCells("A1:N1");
ranking.getRange("A1").values = [[title]];
ranking.mergeCells("A2:N2");
ranking.getRange("A2").values = [[`范围：${scopeLabels[input.scope] || input.scope || "未说明"}｜商品数：${products.length}｜抓取时间：${input.captured_at || "未提供"}`]];
ranking.mergeCells("A3:N3");
ranking.getRange("A3").values = [[warning]];
ranking.getRange("A5:N5").values = [["销量排名", "商品图片", "商品名称", "价格（元）", "当前累计销量", "复查累计销量", "近7天销量", "状态", "商品ID", "推广ID", "商品链接", "数据来源", "销量质量", "备注"]];

const rankedSales = products.map(salesValue).filter((value) => value != null && value >= 0);
const rows = products.map((product) => {
  const productSales = salesValue(product);
  const salesRank = productSales == null || productSales < 0 ? null : 1 + rankedSales.filter((value) => value > productSales).length;
  return [
  salesRank,
  "",
  product.title || "",
  product.price,
  product.current_cumulative_sales,
  product.followup_cumulative_sales,
  product.sales_7d,
  product.status || "",
  product.product_id ? `'${product.product_id}` : "",
  product.promotion_id ? `'${product.promotion_id}` : "",
  product.product_url || "",
  product.source || "",
  product.sales_quality || "unavailable",
  product.current_cumulative_sales != null && product.followup_cumulative_sales != null && product.followup_cumulative_sales < product.current_cumulative_sales
    ? [product.notes, "累计销量下降，疑似商品重置或统计口径变化；不计入排名。"].filter(Boolean).join("；")
    : product.notes || "",
];
});
ranking.getRange(`A${startRow}:N${endRow}`).values = rows;

for (let row = startRow; row <= endRow; row += 1) {
  const product = products[row - startRow];
  const negativeSnapshot = product.current_cumulative_sales != null && product.followup_cumulative_sales != null && product.followup_cumulative_sales < product.current_cumulative_sales;
  if (product.sales_7d == null && !negativeSnapshot) {
    ranking.getRange(`G${row}`).formulas = [[`=IF(OR(E${row}="",F${row}=""),"",F${row}-E${row})`]];
  }
}

ranking.tables.add(`A5:N${endRow}`, true, "DouyinProductRankingTable").style = "TableStyleMedium2";
ranking.freezePanes.freezeRows(5);
ranking.getRange(`A1:N${endRow}`).format.font = { name: "Microsoft YaHei", size: 10, color: "#1F2937" };
ranking.getRange("A1:N1").format = { fill: "#0F172A", font: { name: "Microsoft YaHei", size: 18, bold: true, color: "#FFFFFF" }, rowHeight: 32, verticalAlignment: "center" };
ranking.getRange("A2:N2").format = { fill: "#E0F2FE", font: { name: "Microsoft YaHei", size: 10, color: "#075985" }, rowHeight: 24, verticalAlignment: "center" };
ranking.getRange("A3:N3").format = { fill: "#FFF7ED", font: { name: "Microsoft YaHei", size: 10, bold: true, color: "#9A3412" }, rowHeight: 30, verticalAlignment: "center", wrapText: true };
ranking.getRange("A5:N5").format = { fill: "#1E3A8A", font: { name: "Microsoft YaHei", size: 10, bold: true, color: "#FFFFFF" }, rowHeight: 28, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
ranking.getRange(`A${startRow}:N${endRow}`).format = { verticalAlignment: "center", wrapText: true, rowHeight: 78 };
ranking.getRange(`D${startRow}:G${endRow}`).format.numberFormat = "#,##0";
ranking.getRange(`I${startRow}:J${endRow}`).format.numberFormat = "@";
ranking.getRange(`A${startRow}:B${endRow}`).format.horizontalAlignment = "center";
ranking.getRange(`D${startRow}:J${endRow}`).format.horizontalAlignment = "center";
ranking.getRange(`A${startRow}:N${endRow}`).format.borders = { bottom: { style: "continuous", color: "#CBD5E1", weight: 1 } };

const widths = [10, 15, 52, 12, 14, 14, 13, 12, 22, 22, 30, 25, 18, 28];
"ABCDEFGHIJKLMN".split("").forEach((column, index) => {
  ranking.getRange(`${column}:${column}`).format.columnWidth = widths[index];
});

async function imageDataUrl(url) {
  const response = await fetch(url, { headers: { "user-agent": "Mozilla/5.0" } });
  if (!response.ok) throw new Error(`Image request failed: ${response.status}`);
  const png = await sharp(Buffer.from(await response.arrayBuffer())).resize(180, 180, { fit: "cover" }).png().toBuffer();
  return `data:image/png;base64,${png.toString("base64")}`;
}

let embeddedImages = 0;
for (let index = 0; index < products.length; index += 1) {
  if (!products[index].image_url) continue;
  try {
    const dataUrl = await imageDataUrl(products[index].image_url);
    ranking.images.add({ dataUrl, anchor: { from: { row: startRow - 1 + index, col: 1, rowOffsetPx: 4, colOffsetPx: 7 }, extent: { widthPx: 84, heightPx: 84 } } });
    embeddedImages += 1;
  } catch {
    ranking.getRange(`B${startRow + index}`).values = [["图片加载失败"]];
  }
}

methodology.mergeCells("A1:H1");
methodology.getRange("A1").values = [["数据口径与使用说明"]];
methodology.getRange("A3:B11").values = [
  ["项目", "说明"],
  ["店铺", input.shop_name || "未提供"],
  ["数据范围", scopeLabels[input.scope] || input.scope || "未提供"],
  ["统计周期", period],
  ["销量口径", basisLabels[input.sales_basis]],
  ["排序规则", hasRankableSales ? "按可用的近7天销量数值降序；未知值置后。" : "未获得可排名的近7天销量，保留来源顺序。"],
  ["快照计算", "近7天销量 = 复查累计销量 - 当前累计销量；两次快照需相隔7天。"],
  ["空白值", "表示数据源未返回，不代表0。"],
  ["补充说明", input.notes || "无"],
];
methodology.getRange("A1:H1").format = { fill: "#0F172A", font: { name: "Microsoft YaHei", size: 18, bold: true, color: "#FFFFFF" }, rowHeight: 32, verticalAlignment: "center" };
methodology.getRange("A3:B3").format = { fill: "#1E3A8A", font: { name: "Microsoft YaHei", size: 11, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center" };
methodology.getRange("A4:B11").format = { font: { name: "Microsoft YaHei", size: 11, color: "#1F2937" }, wrapText: true, verticalAlignment: "center", rowHeight: 42 };
methodology.getRange("A4:A11").format = { fill: "#EFF6FF", font: { name: "Microsoft YaHei", size: 11, bold: true, color: "#1E3A8A" }, verticalAlignment: "center" };
methodology.getRange("A:A").format.columnWidth = 18;
methodology.getRange("B:B").format.columnWidth = 86;
methodology.freezePanes.freezeRows(3);

const resolvedOutput = path.resolve(outputPath);
await fs.mkdir(path.dirname(resolvedOutput), { recursive: true });
const preview = await workbook.render({ sheetName: "商品排行", range: `A1:N${Math.min(endRow, 12)}`, scale: 1, format: "png" });
const previewPath = resolvedOutput.replace(/\.xlsx$/i, ".preview.png");
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
const inspection = await workbook.inspect({ kind: "sheet,region,formula", range: `A1:N${endRow}`, maxChars: 12000, options: { maxResults: 300 } });
const inspectionText = inspection.ndjson ?? JSON.stringify(inspection, null, 2);
const formulaErrors = (inspectionText.match(/#REF!|#DIV\/0!|#VALUE!|#NAME\?|#N\/A/g) || []).length;
if (formulaErrors > 0) throw new Error(`Workbook contains ${formulaErrors} formula errors`);
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(resolvedOutput);

console.log(JSON.stringify({ output: resolvedOutput, preview: previewPath, products: products.length, embedded_images: embeddedImages, formula_errors: formulaErrors, has_rankable_sales: hasRankableSales }, null, 2));
