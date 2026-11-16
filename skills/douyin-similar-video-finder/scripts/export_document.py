#!/usr/bin/env python3
"""Validate a Douyin selection JSON and export a linked Word/Markdown list."""

import argparse
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zipfile


class SelectionError(ValueError):
    pass


def text(value, field, required=False):
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise SelectionError(f"{field}: expected {'non-empty ' if required else ''}text")
    return value.strip()


def video_id(value, field):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise SelectionError(f"{field}: ID must be a decimal string or integer, never a float")
    value = str(value)
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise SelectionError(f"{field}: invalid video ID {value!r}")
    return value


def positive_int(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SelectionError(f"{field}: expected a non-negative integer")
    return value


def display_likes(value, field):
    normalized = value.replace(",", "").replace("，", "").strip()
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([万千亿wWkK]?)", normalized)
    if not match:
        raise SelectionError(f"{field}: unknown or ambiguous like display {value!r}")
    multiplier = {"": 1, "千": 1000, "k": 1000, "K": 1000,
                  "万": 10000, "w": 10000, "W": 10000, "亿": 100000000}[match.group(2)]
    amount = Decimal(match.group(1)) * multiplier
    if amount != amount.to_integral_value():
        raise SelectionError(f"{field}: display does not map to an integer")
    return int(amount)


def canonical_id(url, field):
    parts = urlsplit(url)
    match = re.fullmatch(r"/video/([1-9][0-9]*)/?", parts.path)
    if (parts.scheme != "https" or parts.netloc not in {"www.douyin.com", "douyin.com"}
            or not match or parts.query or parts.fragment):
        raise SelectionError(f"{field}: expected https://www.douyin.com/video/ID")
    return match.group(1)


def reference_url(url, field):
    if not url:
        return ""
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.netloc == "v.douyin.com":
        if re.fullmatch(r"/[A-Za-z0-9_-]+/?", parts.path) and not parts.query and not parts.fragment:
            return ""
    return canonical_id(url, field)


def normalize(data):
    if not isinstance(data, dict):
        raise SelectionError("root: expected an object")
    categories = data.get("categories")
    if not isinstance(categories, list) or not categories:
        raise SelectionError("categories: expected a non-empty array")
    min_likes = positive_int(data.get("minLikes", 1000), "minLikes")
    target_per_category = positive_int(data.get("targetPerCategory", 10), "targetPerCategory")
    if not target_per_category:
        raise SelectionError("targetPerCategory: expected a positive integer")
    if not isinstance(data.get("excludedIds", []), list):
        raise SelectionError("excludedIds: expected an array of video IDs")
    excluded_ids = set()
    for index, value in enumerate(data.get("excludedIds", []), 1):
        excluded_ids.add(video_id(value, f"excludedIds[{index}]"))
    result = {
        "title": text(data.get("title", "抖音相似风格视频分类清单"), "title", True),
        "date": text(data.get("date", date.today().isoformat()), "date", True),
        "intro": text(data.get("intro", ""), "intro"),
        "minLikes": min_likes,
        "targetPerCategory": target_per_category,
        "excludedIds": sorted(excluded_ids),
        "categories": [],
    }
    try:
        date.fromisoformat(result["date"])
    except ValueError as exc:
        raise SelectionError("date: expected YYYY-MM-DD") from exc
    all_references = set()
    all_candidates = set()
    for ci, category in enumerate(categories, 1):
        field = f"categories[{ci}]"
        if not isinstance(category, dict):
            raise SelectionError(f"{field}: expected an object")
        group = {"name": text(category.get("name"), f"{field}.name", True),
                 "focus": text(category.get("focus", ""), f"{field}.focus"),
                 "references": [], "items": []}
        if "references" in category:
            if any(category.get(key) for key in ("reference", "referenceUrl", "referenceCanonical")):
                raise SelectionError(f"{field}: use references OR single reference fields, not both")
            references = category["references"]
            if not isinstance(references, list) or not references:
                raise SelectionError(f"{field}.references: expected a non-empty array")
        else:
            references = [category]
        for ri, source in enumerate(references, 1):
            rf = f"{field}.references[{ri}]"
            if not isinstance(source, dict):
                raise SelectionError(f"{rf}: expected an object")
            ref = {key: text(source.get(key, ""), f"{rf}.{key}", key == "reference")
                   for key in ("reference", "referenceUrl", "referenceCanonical")}
            url_id = reference_url(ref["referenceUrl"], f"{rf}.referenceUrl")
            ref_id = canonical_id(ref["referenceCanonical"], f"{rf}.referenceCanonical") if ref["referenceCanonical"] else ""
            if url_id and ref_id and url_id != ref_id:
                raise SelectionError(f"{rf}: reference URL and canonical ID disagree")
            if ref_id:
                ref["referenceCanonical"] = f"https://www.douyin.com/video/{ref_id}"
            if ref_id or url_id:
                all_references.add(ref_id or url_id)
            group["references"].append(ref)
        items = category.get("items")
        if not isinstance(items, list):
            raise SelectionError(f"{field}.items: expected an array (empty is allowed)")
        for ii, source in enumerate(items, 1):
            itf = f"{field}.items[{ii}]"
            if not isinstance(source, dict):
                raise SelectionError(f"{itf}: expected an object")
            item = {"id": video_id(source.get("id"), f"{itf}.id")}
            if item["id"] in excluded_ids:
                raise SelectionError(f"{itf}: candidate is in excludedIds {item['id']}")
            if item["id"] in all_candidates:
                raise SelectionError(f"{itf}: duplicate candidate ID {item['id']}")
            all_candidates.add(item["id"])
            for key in ("author", "title", "similarity"):
                item[key] = text(source.get(key), f"{itf}.{key}", True)
            item["styleDimensions"] = source.get("styleDimensions")
            if (not isinstance(item["styleDimensions"], list)
                    or len(item["styleDimensions"]) < 2
                    or any(not isinstance(value, str) or not value.strip() for value in item["styleDimensions"])):
                raise SelectionError(f"{itf}.styleDimensions: provide at least two observed matching dimensions")
            item["styleDimensions"] = [value.strip() for value in item["styleDimensions"]]
            item["likes"] = positive_int(source.get("likes"), f"{itf}.likes")
            if item["likes"] < min_likes:
                raise SelectionError(f"{itf}.likes: {item['likes']} is below minimum {min_likes}")
            for key in ("key", "duration", "match", "likesDisplay", "likesCheckedAt", "likesEvidence"):
                item[key] = text(source.get(key, ""), f"{itf}.{key}")
            for key in ("likesDisplay", "likesCheckedAt", "likesEvidence"):
                if not item[key]:
                    raise SelectionError(f"{itf}.{key}: required for the like threshold audit")
            shown_likes = display_likes(item["likesDisplay"], f"{itf}.likesDisplay")
            if shown_likes != item["likes"]:
                raise SelectionError(f"{itf}: likes must equal the numeric conversion of likesDisplay")
            supplied = text(source.get("url", ""), f"{itf}.url")
            if supplied and canonical_id(supplied, f"{itf}.url") != item["id"]:
                raise SelectionError(f"{itf}: candidate URL does not match ID {item['id']}")
            item["url"] = f"https://www.douyin.com/video/{item['id']}"
            group["items"].append(item)
        result["categories"].append(group)
    overlap = all_candidates & all_references
    if overlap:
        raise SelectionError(f"original reference included as a new recommendation: {', '.join(sorted(overlap))}")
    result["deficits"] = [
        {"category": group["name"], "count": len(group["items"]), "target": target_per_category}
        for group in result["categories"] if len(group["items"]) < target_per_category
    ]
    return result


def total(data):
    return sum(len(group["items"]) for group in data["categories"])


def display_reference(ref):
    url = ref["referenceUrl"] or ref["referenceCanonical"]
    status = "（无链接参考）" if not url else "（原视频未核验）" if not ref["referenceCanonical"] else ""
    return ref["reference"] + status, url


def likes_summary(item):
    shown = item["likesDisplay"]
    if re.search(r"[万千亿wWkK]", shown):
        return f"{shown}（按显示值换算约 {item['likes']}，非精确计数）"
    return shown


def export_docx(data, output):
    try:
        from docx import Document
        from docx.shared import Cm, Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
    except ImportError as exc:
        raise SelectionError("python-docx is required for Word export; use the documents runtime or install that dependency") from exc
    document = Document()
    section = document.sections[0]
    section.page_height, section.page_width = Inches(11), Inches(8.5)
    section.top_margin, section.bottom_margin = Cm(1.8), Cm(1.8)
    section.left_margin = section.right_margin = Cm(2)
    section.header_distance = section.footer_distance = Cm(.7)
    for name in ("Normal", "Title", "Subtitle", "Heading 1", "Heading 2"):
        style = document.styles[name]
        style.font.name, style.font.italic = "Microsoft YaHei", False
        style.font.color.rgb = RGBColor(0, 0, 0)
        style._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Microsoft YaHei")
        style.paragraph_format.line_spacing = 1.18
    for border in list(document.styles._element.iter(qn("w:pBdr"))):
        border.getparent().remove(border)
    for name, size, before, after in (("Normal", 11, 0, 5), ("Title", 21, 0, 9),
                                      ("Subtitle", 9.5, 0, 10), ("Heading 1", 16, 0, 8),
                                      ("Heading 2", 11.5, 10, 5)):
        style = document.styles[name]
        style.font.size = Pt(size)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
    expected_links = set()

    def link(url):
        expected_links.add(url)
        paragraph = document.add_paragraph()
        rel = paragraph.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
        node = OxmlElement("w:hyperlink")
        node.set(qn("r:id"), rel)
        run, props = OxmlElement("w:r"), OxmlElement("w:rPr")
        for tag, value in (("color", "1261A0"), ("u", "single"), ("sz", "20")):
            element = OxmlElement(f"w:{tag}")
            element.set(qn("w:val"), value)
            props.append(element)
        run.append(props)
        value = OxmlElement("w:t")
        value.text = url
        run.append(value)
        node.append(run)
        paragraph._p.append(node)

    def detail(label, value):
        paragraph = document.add_paragraph()
        paragraph.add_run(label).bold = True
        paragraph.add_run(value)
        paragraph.paragraph_format.keep_with_next = True

    document.add_paragraph(data["title"], style="Title")
    document.add_paragraph(
        f"整理日期 {data['date']}  共 {len(data['categories'])} 类风格 {total(data)} 条新推荐  每类目标 {data['targetPerCategory']} 条  点赞门槛 {data['minLikes']}",
        style="Subtitle",
    )
    if data["intro"]:
        document.add_paragraph(data["intro"])
    if data["deficits"]:
        document.add_paragraph("数量缺口：" + "；".join(
            f"{entry['category']} {entry['count']}/{entry['target']} 条" for entry in data["deficits"]
        ))
    for ci, group in enumerate(data["categories"], 1):
        if ci > 1:
            document.add_page_break()
        document.add_paragraph(f"{ci}  {group['name']}  {len(group['items'])}条", style="Heading 1")
        if group["focus"]:
            document.add_paragraph(group["focus"])
        for ref in group["references"]:
            label, url = display_reference(ref)
            detail("原始参考  ", label)
            if url:
                link(url)
        if not group["items"]:
            document.add_paragraph("本类暂无通过核验的新推荐。")
        for ii, item in enumerate(group["items"], 1):
            document.add_paragraph(f"{ci} {ii}  {item['author']}", style="Heading 2")
            detail("作品  ", item["title"])
            detail("相似点与差异  ", item["similarity"])
            detail("点赞  ", f"{likes_summary(item)}；详情页点赞区核验于 {item['likesCheckedAt']}")
            link(item["url"])
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.paragraph_format.space_before = footer.paragraph_format.space_after = Pt(0)
    page_run = footer.add_run()
    page_run.font.name, page_run.font.size = "Microsoft YaHei", Pt(9)
    page_run.font.color.rgb = RGBColor(0, 0, 0)
    page_run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Microsoft YaHei")
    page_field = OxmlElement("w:fldSimple")
    page_field.set(qn("w:instr"), "PAGE")
    page_field.append(page_run._r)
    footer._p.append(page_field)
    document.core_properties.title = data["title"]
    document.core_properties.author = ""
    document.core_properties.subject = "抖音分类视频链接清单"
    output.parent.mkdir(parents=True, exist_ok=True)
    document.save(output)
    with zipfile.ZipFile(output) as archive:
        relations = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
        actual = {rel.attrib["Target"] for rel in relations if rel.attrib.get("Type", "").endswith("/hyperlink")}
        if actual != expected_links:
            raise SelectionError("generated Word hyperlink targets do not match the selection")
    return len(expected_links)


def export_markdown(data, output):
    def escape(value):
        return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("\n", " ")
    lines = [f"# {escape(data['title'])}", "", f"{data['date']} · {len(data['categories'])} 类 · {total(data)} 条新推荐 · 每类目标 {data['targetPerCategory']} 条 · 点赞门槛 {data['minLikes']}+", ""]
    if data["intro"]:
        lines.extend([escape(data["intro"]), ""])
    if data["deficits"]:
        lines.extend(["数量缺口：" + "；".join(
            f"{escape(entry['category'])} {entry['count']}/{entry['target']} 条" for entry in data["deficits"]
        ), ""])
    for ci, group in enumerate(data["categories"], 1):
        lines.extend([f"## {ci} {escape(group['name'])}", "", escape(group["focus"]), ""])
        for ref in group["references"]:
            label, url = display_reference(ref)
            lines.extend([f"原始参考：{escape(label)}", ""])
            if url:
                lines.extend([f"[{url}]({url})", ""])
        if not group["items"]:
            lines.extend(["本类暂无通过核验的新推荐。", ""])
        for ii, item in enumerate(group["items"], 1):
            lines.extend([f"### {ci}.{ii} {escape(item['author'])}｜{escape(item['title'])}", "",
                          f"相似点与差异：{escape(item['similarity'])}", "",
                          f"匹配维度：{escape('、'.join(item['styleDimensions']))}", "",
                          f"点赞：{escape(likes_summary(item))}；核验于 {escape(item['likesCheckedAt'])}", "",
                          f"点赞证据：{escape(item['likesEvidence'])}", ""])
            for label, key in (("匹配说明", "match"), ("时长", "duration")):
                if item[key]:
                    lines.extend([f"{label}：{escape(item[key])}", ""])
            lines.extend([f"[{item['url']}]({item['url']})", ""])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="UTF-8 selection JSON")
    parser.add_argument("--output", type=Path, help="destination .docx")
    parser.add_argument("--markdown", type=Path, help="optional companion .md")
    parser.add_argument("--validate-only", action="store_true", help="validate without exporting (python-docx not needed)")
    args = parser.parse_args()
    if not args.validate_only and not args.output:
        parser.error("--output is required unless --validate-only is used")
    try:
        data = normalize(json.loads(args.input.read_text(encoding="utf-8-sig")))
        report = {"categories": len(data["categories"]), "recommended": total(data), "validated": True,
                  "minLikes": data["minLikes"], "targetPerCategory": data["targetPerCategory"],
                  "deficits": data["deficits"]}
        if not args.validate_only:
            output = args.output.resolve()
            if output == args.input.resolve() or (args.markdown and args.markdown.resolve() in {args.input.resolve(), output}):
                raise SelectionError("input, Word output, and Markdown output must have distinct paths")
            if output.suffix.lower() != ".docx":
                raise SelectionError("--output must end in .docx")
            report["hyperlinks"] = export_docx(data, output)
            report["output"] = str(output)
            if args.markdown:
                export_markdown(data, args.markdown.resolve())
                report["markdown"] = str(args.markdown.resolve())
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (SelectionError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
