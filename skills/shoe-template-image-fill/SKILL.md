---
name: shoe-template-image-fill
description: Fill shoe peer-template Excel workbooks with product images. Use when the user wants main images and detail-page images inserted into a footwear template spreadsheet, usually one competitor column at a time, with rows like main image 1-5 followed by detail image template rows.
---

# Shoe Template Image Fill

Use this skill to insert downloaded footwear product images into a peer-template spreadsheet.

## Workflow

1. Confirm the workbook path, image folder, and target competitor column.
2. Use `scripts/fill_shoe_template_images.py`.
3. Fill only the requested target column unless the user explicitly asks to fill more columns.
4. Map images in this order:
   - `main_images/main_01.*` through `main_05.*` -> rows 2-6 by default.
   - `detail_images/detail_01.*` onward -> rows 7 onward by default.
5. Convert WebP or other source formats to PNG before embedding for Excel compatibility.
6. Save a new output workbook; do not overwrite the user's source workbook unless explicitly asked.

## Command

```powershell
python scripts/fill_shoe_template_images.py `
  --template "C:\path\template.xlsx" `
  --images "C:\path\downloaded_images_folder" `
  --output "C:\path\filled.xlsx" `
  --column-header "苏茵茵"
```

Expected image folder layout:

```text
downloaded_images_folder/
  main_images/
    main_01.webp
    main_02.webp
  detail_images/
    detail_01.jpg
    detail_02.jpg
```

If the target column header is missing, create it in the first empty column only when the user asks; otherwise stop and explain.

