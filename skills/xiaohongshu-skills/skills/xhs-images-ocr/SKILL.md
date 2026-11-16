---
name: xhs-images-ocr
description: 保存小红书笔记图片，用本地 Tesseract 识别中英文并合并逐图文字。网页取图使用真实 Ego，已保存图片可离线处理。
---

# 小红书图片文字识别

先读 [本机 Ego 执行方式](../../references/local-ego-execution.md)。

1. 已有本地图片直接处理；只有笔记链接时用 Ego 核对标题、作者、图片数量与顺序，再保存原图。只需下载时不执行 OCR。
2. 记录逐图来源、顺序与绝对路径。只拿到封面或部分图片时说明缺口。
3. 直接用本项目纯本地 scripts/image_ocr.py 的 ocr_image / ocr_images，不启动浏览器。

```python
import sys
sys.path.insert(0, r'C:\Users\TTT\.codex\skills\xiaohongshu-skills\scripts')
from image_ocr import ocr_images, parse_ocr_content
items = ocr_images(
    [r'C:\absolute\image-001.png'],
    lang='chi_sim+eng',
    tesseract_cmd=r'C:\Users\TTT\.local\share\ops-skills-20261114\tools\tesseract\tesseract.exe',
)
combined = parse_ocr_content([item['text'] for item in items])
```

执行解释器：C:/Users/TTT/.local/share/ops-skills-20261114/.venv/Scripts/python.exe -X utf8。语言包目录为 C:/Users/TTT/.local/share/ops-skills-20261114/tools/tesseract/tessdata，含 chi_sim、eng。

保留逐图文字和合并结果，数字、网址和专名对照图片校正，无法确定处标注不清。已验证本机中文 OCR 可运行，不保证每张图准确。不运行依赖 Chrome/Bridge 的 cli.py images-ocr 替代 Ego 取图；原说明和代码保留作参考。
