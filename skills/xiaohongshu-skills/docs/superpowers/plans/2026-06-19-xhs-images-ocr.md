# XHS Images OCR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CLI command that downloads a Xiaohongshu note's images, runs local OCR, and returns parsed text content as JSON.

**Architecture:** Reuse `get_feed_detail` and `process_images` from the existing image download flow. Add a small `scripts/image_ocr.py` module that shells out to local Tesseract, cleans recognized text, and merges per-image text in image order.

**Tech Stack:** Python 3.11+, argparse, requests-based downloader, local `tesseract` CLI.

## Global Constraints

- CLI output must be JSON with `ensure_ascii=False`.
- Default image output directory is `/tmp/xhs_images`.
- Downloading XHS CDN images must use `https://www.xiaohongshu.com/` as `Referer`.
- OCR must fail with a clear error if the local `tesseract` command is unavailable or returns an error.

---

### Task 1: OCR Module

**Files:**
- Create: `scripts/image_ocr.py`
- Test: `tests/test_image_ocr.py`

**Interfaces:**
- Produces: `ocr_image(image_path: str, lang: str = "chi_sim+eng", tesseract_cmd: str = "tesseract") -> str`
- Produces: `ocr_images(image_paths: list[str], lang: str = "chi_sim+eng", tesseract_cmd: str = "tesseract") -> list[dict[str, str]]`
- Produces: `parse_ocr_content(texts: list[str]) -> str`

- [ ] Write failing tests for Tesseract invocation and text cleanup.
- [ ] Run `uv run pytest tests/test_image_ocr.py -q` and confirm failure.
- [ ] Implement minimal OCR module.
- [ ] Run `uv run pytest tests/test_image_ocr.py -q` and confirm pass.

### Task 2: CLI Command

**Files:**
- Modify: `scripts/cli.py`
- Test: `tests/test_images_ocr_cli.py`

**Interfaces:**
- Consumes: `_detail_image_urls(detail) -> list[str]`
- Consumes: `process_images(images: list[str], save_dir: str | None = None) -> list[str]`
- Consumes: `ocr_images(...)` and `parse_ocr_content(...)`
- Produces: `images-ocr` CLI command with `--feed-id`, `--xsec-token`, `--output-dir`, `--ocr-lang`, and `--tesseract-cmd`.

- [ ] Write failing parser/command test for `images-ocr`.
- [ ] Run `uv run pytest tests/test_images_ocr_cli.py -q` and confirm failure.
- [ ] Add `cmd_images_ocr` and parser registration.
- [ ] Run `uv run pytest tests/test_images_ocr_cli.py -q` and confirm pass.

### Task 3: Documentation and Verification

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] Document `images-ocr` usage and local Tesseract requirement.
- [ ] Run `uv run pytest -q`.
- [ ] Run `uv run ruff check scripts/image_ocr.py tests/test_image_ocr.py tests/test_images_ocr_cli.py`.
- [ ] Run `git diff --check`.
