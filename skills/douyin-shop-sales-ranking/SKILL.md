---
name: douyin-shop-sales-ranking
description: Analyze a Douyin product share link or copied product message, identify its shop, collect shop products with images and prices, verify the meaning and provenance of sales fields, and export a ranked Excel workbook or a seven-day snapshot monitor. Use when the user asks for a Douyin shop's recent 7-day product sales ranking, competitor product ranking, store product images/prices/sales, or a sortable Excel report from a Douyin product link. Also use when the task requires determining whether public sales data is exact, estimated, cumulative, or unavailable.
---

# Douyin Shop Sales Ranking

## Core rule

Never label cumulative sales, live-room order, views, cart additions, favorites, daily sales, or 30-day sales as recent 7-day sales. Leave unavailable values blank and state the limitation.

Treat products as identical only when their stable product or promotion IDs match. Keep same-title or same-image relistings separate.

## Required companion skills

- Read `C:/Users/TTT/.agents/skills/ego-browser/SKILL.md`, run the installed `ego-browser skill`, and operate only real Ego / ego(lite). Follow its TaskSpace, snapshot, action, and verification workflow; preserve user-owned tabs and hand off login or human verification to the user.
- Read and use the spreadsheet skill before creating `.xlsx` output. Use `@oai/artifact-tool`, render a preview, inspect formulas, and verify embedded images.
- Use `douyin-product-image-export/SKILL.md` only when the user additionally requests full main/detail image folders.

## Workflow

### 1. Parse and resolve the product

Extract every available title, share code, URL, promotion ID, product ID, and timestamp from the copied message. Resolve the product in the current browser session. Record the exact source item separately from any same-title item later found in the shop or live cart.

### 2. Identify the shop and requested scope

Capture shop name and all available shop IDs. Distinguish these scopes:

- Full active shop catalog
- Current live-room cart
- Creator showcase
- One product plus related products

Never describe a live-cart subset as the full shop. State the observed item count and the expected full-shop count when both are known.

### 3. Choose the strongest sales source

Use this priority order:

1. Merchant backend export for the requested 7-day date range: exact and preferred.
2. Authorized analytics account exposing a named 7-day field: exact or platform-estimated according to its label.
3. Public source with a clearly dated 7-day field and complete requested scope: preserve its exact/estimated label.
4. Official Douyin public product/live data: use for images, current prices, IDs, status, and only sales fields explicitly returned.
5. Two cumulative-sales snapshots exactly seven days apart: calculate `later - earlier`; label the period and snapshot times.

If levels 1-3 are unavailable and no historical snapshot exists, do not produce a historical 7-day ranking. Produce a public-data snapshot workbook and explain what input would unlock the ranking.

### 4. Collect official public product data

Read [references/official-data.md](references/official-data.md) before using public endpoints. Prefer requests naturally issued by the Douyin page. Reuse current cookies and page JavaScript when signed parameters are required.

For each item, normalize:

- `product_id` and `promotion_id` as text
- title, image URL, product URL, shop ID
- current price in yuan; convert cents only when the source field is documented as cents
- availability and source position
- cumulative sales, 7-day sales, and sales quality as separate fields
- capture time and source URL or endpoint

### 5. Validate before ranking

Apply these checks:

- Confirm the date range is seven days and include both start and end dates.
- Confirm whether the field is units, orders, or GMV.
- Confirm the scope covers the requested shop rather than a live subset.
- Keep exact, estimated, interval, cumulative, and unavailable values distinct.
- Reject negative snapshot differences as a relisting/reset warning rather than sales.
- Sort only numeric 7-day sales values descending; place unknown values last and never convert blanks to zero.

### 6. Export the workbook

Normalize data to the schema in [references/workbook-input.md](references/workbook-input.md), then run:

```powershell
$env:NODE_PATH='<bundled node_modules path>'
node scripts/build_ranking.mjs input.json output.xlsx
```

The builder embeds product images, preserves long IDs as text, writes prices as numbers, adds snapshot-difference formulas, and creates a methodology sheet. It writes a sibling preview PNG.

If the user requests only a quick answer, still include the scope and sales basis. For a workbook, include source, capture time, exact period, product links, and a visible warning when 7-day sales are unavailable.

### 7. Verify and hand off

- Inspect the workbook for `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, and `#N/A`.
- Render the top section and visually inspect wrapping, widths, headers, and prices.
- Verify the XLSX contains one embedded image per successfully downloaded product image.
- Report the number of products, data scope, sales basis, missing fields, and output file.

## Stop conditions

Do not bypass authentication, defeat access controls, or claim hidden values. If exact historical 7-day data needs a merchant export or authorized login, deliver the best public snapshot and ask for that specific input.
