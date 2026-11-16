# Workbook builder input

Run `scripts/build_ranking.mjs <input.json> <output.xlsx>` after loading the bundled Node.js dependencies.

## JSON shape

```json
{
  "shop_name": "Example shop",
  "scope": "full_shop | live_cart | showcase | related",
  "captured_at": "2026-08-08 17:40 Asia/Shanghai",
  "period_start": "2026-08-02",
  "period_end": "2026-08-08",
  "sales_basis": "exact_7d | estimated_7d | snapshot_delta | snapshot_pending | unavailable",
  "notes": "Optional global note",
  "products": [
    {
      "source_order": 1,
      "product_id": "3827591927218438330",
      "promotion_id": "3827596054589735096",
      "title": "Product title",
      "image_url": "https://...",
      "product_url": "https://...",
      "price": 239,
      "current_cumulative_sales": 260,
      "followup_cumulative_sales": null,
      "sales_7d": null,
      "sales_quality": "cumulative_only",
      "status": "在售",
      "source": "Douyin public product page",
      "notes": "Optional row note"
    }
  ]
}
```

## Field rules

- Store IDs as JSON strings.
- Store price in yuan as a number.
- Store unknown numeric values as `null`, never `0`.
- Provide `sales_7d` only when the source explicitly supports that meaning.
- For snapshot monitoring, provide `current_cumulative_sales`; add `followup_cumulative_sales` after seven days.
- Keep same-title products when IDs differ.
- Use an explicit `scope`; `live_cart` must not be presented as `full_shop`.
