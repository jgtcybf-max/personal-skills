"""Prepare local canvas inputs and review evidence once; never upload or generate."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
MATERIALS = HERE.parent.parent / 'superdirector-canvas-upload' / 'scripts' / 'materials.py'
REVIEW = HERE / 'review_media.py'
ANALYSIS_TEMPLATE = HERE.parent / 'assets' / 'material-analysis-prompt.txt'
GENERATION_TEMPLATE = HERE.parent / 'assets' / 'video-generation-prompt-template.txt'


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def signature(path):
    before = path.stat()
    value = {'path': str(path), 'bytes': before.st_size,
             'mtime_ns': before.st_mtime_ns, 'sha256': sha256(path)}
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Input changed while hashing: ' + str(path))
    return value


def load_materials():
    spec = importlib.util.spec_from_file_location('sd_materials', MATERIALS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def json_write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def run_script(script, arguments):
    result = subprocess.run([sys.executable, '-X', 'utf8', str(script), *arguments],
                            capture_output=True, encoding='utf-8', timeout=300,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        # Child scripts are local allowlisted helpers, but do not relay raw media metadata.
        raise RuntimeError(f'{script.name} failed (exit {result.returncode}); inspect task inputs and partial output')


def make_product_sheet(images, target):
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 17)
    except OSError:
        font = ImageFont.load_default()
    columns = min(4, len(images))
    canvas = Image.new('RGB', (columns * 320, math.ceil(len(images) / columns) * 354), '#eeeeee')
    draw = ImageDraw.Draw(canvas)
    for index, path in enumerate(images):
        x, y = (index % columns) * 320, (index // columns) * 354
        with Image.open(path) as original:
            picture = ImageOps.exif_transpose(original).convert('RGB')
            picture.thumbnail((310, 310), Image.Resampling.LANCZOS)
            canvas.paste(picture, (x + (320 - picture.width) // 2, y + 38))
        draw.text((x + 5, y + 6), f'{index + 1}. {path.name[:28]}', font=font, fill='black')
    canvas.save(target, quality=90)


def prepare(args):
    started = time.perf_counter()
    video = Path(args.video).expanduser().resolve(strict=True)
    if not video.is_file():
        raise ValueError('--video must name one exact video file')
    materials = load_materials()
    if video.suffix.lower() not in materials.VIDEO_EXTENSIONS:
        raise ValueError('--video extension is not recognized')
    images = materials.collect(args.images, materials.IMAGE_EXTENSIONS, False)
    if not images or len(images) > 200:
        raise ValueError('Supply between 1 and 200 product images')
    prompt = Path(args.prompt_file).expanduser().resolve(strict=True) if args.prompt_file else None
    if prompt and not prompt.is_file():
        raise ValueError('--prompt-file must be an existing file')
    source_files = [video, *images] + ([prompt] if prompt else [])
    source_signatures = [signature(p) for p in source_files]
    if any(s['bytes'] == 0 for s in source_signatures):
        raise ValueError('Empty input file')
    script_signatures = {p.name: sha256(p) for p in (Path(__file__).resolve(), MATERIALS, REVIEW)}
    template_signatures = {p.name: sha256(p) for p in (ANALYSIS_TEMPLATE, GENERATION_TEMPLATE)}
    identity = {'source_signatures': source_signatures, 'script_sha256': script_signatures,
                'template_sha256': template_signatures,
                'focus': args.focus, 'batch_size': args.batch_size}
    output = Path(args.out).expanduser().resolve()
    session_file = output / 'session.json'
    if output.exists():
        if not args.reuse:
            raise ValueError('Output exists; use a new directory or --reuse for verified unchanged input')
        session = json.loads(session_file.read_text(encoding='utf-8'))
        if session.get('identity') != identity:
            raise ValueError('Cached input, options or helper version changed; choose a new output directory')
        for artifact in session['artifact_signatures']:
            path = output / artifact['relative_path']
            if not path.is_file() or sha256(path) != artifact['sha256']:
                raise ValueError('Cached artifact missing or changed; choose a new output directory')
        return {'status': 'reused', 'session': str(session_file),
                'operation_card': str(output / '操作卡.md'),
                'wall_clock_seconds': round(time.perf_counter() - started, 4)}
    output.mkdir(parents=True, exist_ok=False)
    try:
        inventory = output / 'upload-manifest.json'
        inventory_args = ['--video', str(video), '--manifest', str(inventory),
                          '--batch-size', str(args.batch_size)]
        for value in args.images:
            inventory_args += ['--images', value]
        run_script(MATERIALS, inventory_args)
        manifest = json.loads(inventory.read_text(encoding='utf-8'))
        if [item['path'] for item in manifest['files']] != [str(p) for p in [video, *images]]:
            raise ValueError('Input inventory changed during preparation; choose a new output directory')
        make_product_sheet(images, output / '商品图总览.jpg')
        review_args = ['--video', str(video), '--out', str(output / 'source-review')]
        for value in args.focus:
            review_args += ['--focus', value]
        run_script(REVIEW, review_args)
        technical = json.loads((output / 'source-review' / 'metadata.json').read_text(encoding='utf-8'))
        if prompt:
            (output / '提示词原文.txt').write_bytes(prompt.read_bytes())
        if materials.collect(args.images, materials.IMAGE_EXTENSIONS, False) != images or [signature(p) for p in source_files] != source_signatures:
            raise ValueError('Inputs changed during preparation; this output must not be reused')
        stamp = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
        summary = {k: technical.get(k) for k in ('width', 'height', 'fps', 'decoded_frames',
                   'duration_from_decoded_frames_seconds', 'has_audio', 'all_declared_frames_decoded')}
        analysis_context = f'''本次待分析素材（自动填入路径和技术信息，不代表已经观看或听审）
原视频：{video}
商品图路径：
''' + '\n'.join(f'- {p}' for p in images) + f'''
实际媒体参数：{json.dumps(summary, ensure_ascii=False)}
本地技术证据目录：{output / 'source-review'}
原片全片总览：{output / 'source-review' / 'overview_24.jpg'}
原片首两帧及尾帧：{output / 'source-review' / 'first2_last.jpg'}
商品图总览：{output / '商品图总览.jpg'}
重点段联系表：{json.dumps([x.get('file') for x in technical.get('focus_sheets', [])], ensure_ascii=False)}
分析完成后由执行者另存：{output / '01_素材分析.md'}
本工具没有生成分析结论、生成提示词定稿或审核通过记录。

'''
        (output / '00_素材分析提示词.txt').write_text(
            analysis_context + ANALYSIS_TEMPLATE.read_text(encoding='utf-8-sig'), encoding='utf-8')
        (output / '02_生成提示词模板.txt').write_text(
            '待填模板，不能直接提交。先完成01_素材分析.md，再按实际画布引用顺序填写；'
            '定稿由执行者另存03_生成提示词_定稿.txt。本工具不自动生成分析或定稿。\n\n'
            + GENERATION_TEMPLATE.read_text(encoding='utf-8-sig'), encoding='utf-8')
        if {p.name: sha256(p) for p in (ANALYSIS_TEMPLATE, GENERATION_TEMPLATE)} != template_signatures:
            raise ValueError('Prompt templates changed during preparation; choose a new output directory')
        card = f'''# 画布任务操作卡

准备时间（北京时间）：{stamp}
原视频：{video}
商品图：{len(images)}张；编号为本地清单顺序，**不是模型引用编号**。
素材清单：{inventory}
商品图总览：{output / '商品图总览.jpg'}
原视频总览及首尾：{output / 'source-review'}
实际媒体参数：{json.dumps(summary, ensure_ascii=False)}

材质成分：本工具未读取用户或商品成分资料，待执行者依据资料确认；看图只写可见表面质感，不能据图推断真皮或PU。
素材分析提示词：{output / '00_素材分析提示词.txt'}；执行者观看素材后另存01_素材分析.md，当前分析未完成。
生成提示词模板：{output / '02_生成提示词模板.txt'}；先依据分析填写，再核对实际画布引用顺序，另存03_生成提示词_定稿.txt；当前仅有待填模板，不能提交。
用户提供提示词：{'已复制为提示词原文.txt，保留原文，尚未验证材质开头及模型引用编号' if prompt else '未提供'}。
画布/节点/引用顺序：未读取应用，待当次核对；已有节点只补缺失。
生成参数：待实际界面核对；要求先480原生1条，通过后由平台直接生成1080一条，按实际UI记录清晰度标签。
费用：未提交，平台实扣未知；本工具没有创建生成任务。
审核：尚未进行商品一致性、动态或音频听审，不能标记通过。

下一步：调用00素材分析提示词并完成01素材分析，依据分析填写02生成模板；画布引用核对后保存03定稿。仅在已授权生成时关闭参数菜单、独立核对实际参数及预计点数，再单独提交一次。下载后使用review_media.py整理证据，480通过才进入1080；1080后本地加原音并核验。
'''
        (output / '操作卡.md').write_text(card, encoding='utf-8')
        artifacts = [{'relative_path': str(p.relative_to(output)), 'sha256': sha256(p)}
                     for p in sorted(output.rglob('*')) if p.is_file()]
        session = {'status': 'prepared', 'prepared_at_beijing': stamp, 'identity': identity,
                   'source_video': str(video), 'images': [str(p) for p in images],
                   'counts': manifest['counts'], 'technical': summary,
                   'material_composition': None, 'semantic_review': 'not_performed',
                   'analysis_status': 'pending', 'generation_prompt_status': 'template_only',
                   'analysis_prompt_file': str(output / '00_素材分析提示词.txt'),
                   'generation_template_file': str(output / '02_生成提示词模板.txt'),
                   'platform_task_created': False, 'actual_compute_points': None,
                   'artifact_signatures': artifacts,
                   'wall_clock_seconds': time.perf_counter() - started}
        json_write(session_file, session)
        return {'status': 'prepared', 'session': str(session_file),
                'operation_card': str(output / '操作卡.md'), 'counts': manifest['counts'],
                'wall_clock_seconds': round(session['wall_clock_seconds'], 4)}
    except Exception as exc:
        json_write(output / 'preparation-error.json', {'error': str(exc), 'reusable': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', required=True)
    parser.add_argument('--images', action='append', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--focus', action='append', default=[])
    parser.add_argument('--batch-size', type=int, default=5)
    parser.add_argument('--prompt-file')
    parser.add_argument('--reuse', action='store_true')
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error('--batch-size must be positive')
    try:
        print(json.dumps(prepare(args), ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
