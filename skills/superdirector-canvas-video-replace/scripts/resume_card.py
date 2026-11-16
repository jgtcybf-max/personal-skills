"""Read the current task record into a compact continuation card; no task writes or UI.

Usage: python resume_card.py --record task-record.json --out continuation
The card is a record snapshot, never proof of live UI state or generation permission.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid


def timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.timestamp() if dt.utcoffset() is not None else float('-inf')
    except (ValueError, TypeError):
        return float('-inf')


def clean(value):
    return str(value if value is not None else '未知').replace('|', '/').replace('\n', ' ')


def build(record: Path, excluded):
    raw = record.read_bytes()
    data = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(data.get('tasks'), list):
        raise ValueError('tasks must be a list')
    tasks = [t for t in data['tasks'] if t.get('submitted') is True]
    pending = [a for a in data.get('pending_attempts', [])
               if not str(a.get('acceptance', '')).startswith('resolved_')]
    products = list(dict.fromkeys([c['product'] for c in data.get('colors', [])] +
                                 [t['product'] for t in tasks] + [a['product'] for a in pending]))

    def path_status(value):
        if not value:
            return '未提供'
        path = Path(value).expanduser()
        path = (record.parent / path).resolve() if not path.is_absolute() else path.resolve()
        if any(path == root or root in path.parents for root in excluded):
            return '排除范围，未访问'
        return '存在' if path.is_file() else '路径缺失'

    rows = []
    for product in products:
        matches = [(i, t) for i, t in enumerate(tasks) if t['product'] == product]
        task = max(matches, key=lambda pair: (timestamp(pair[1].get('submitted_at')), pair[0]))[1] if matches else {}
        unresolved = [a for a in pending if a['product'] == product]
        review = task.get('review') or {}
        audio = task.get('audio') or {}
        audio_review = audio.get('review') or {}
        video_status = path_status(task.get('file'))
        review_status = path_status(review.get('evidence'))
        audio_status = path_status(audio.get('file'))
        if unresolved:
            next_action = '核原节点受理状态；禁止补点生成'
            desktop = True
        elif not task:
            next_action = '核本款素材与当前授权；无已提交任务'
            desktop = None
        elif video_status != '存在':
            next_action = ('已记失败：保留失败证据，核最新政策；不自动重试'
                           if '失败' in str(task.get('status', ''))
                           else '核原节点终态或现有下载路径；只下载同任务')
            desktop = '失败' not in str(task.get('status', ''))
        elif review.get('verdict') in ('有瑕疵', '不通过') and review_status == '存在':
            next_action = '保留问题片和报告；不自动升级或重试'
            desktop = False
        elif review.get('verdict') != '通过' or review_status != '存在':
            next_action = '对现有下载补画面审核；已有证据先复用'
            desktop = False
        elif task.get('stage') == '480':
            next_action = '480画面已审：核最新政策/当前UI后推进已授权1080；480原音只按本任务明确验收要求处理'
            desktop = None
        elif audio_status != '存在':
            next_action = '对现有下载本地配对应原音并核时序；不生成'
            desktop = False
        elif audio_review.get('verdict') != '通过' or path_status(audio_review.get('evidence')) != '存在':
            next_action = '原音已存在：补首中尾听审/同步/播放器兼容未完成项'
            desktop = False
        else:
            next_action = '核归档/交付清单；已完成项不重做'
            desktop = False
        rows.append({'product': product, 'stage': task.get('stage'),
                     'node_id': task.get('node_id'), 'task_id': task.get('task_id'),
                     'submitted_at': task.get('submitted_at'), 'status': task.get('status'),
                     'video': task.get('file'), 'video_path_status': video_status,
                     'output_metadata_from_record': task.get('output_metadata'),
                     'expected_points': task.get('expected_points'),
                     'debit': task.get('debit'), 'refund': task.get('refund'),
                     'parent480': task.get('parent480_key') or task.get('parent480'),
                     'prompt_file': task.get('prompt_file'),
                     'parameter_evidence': task.get('parameter_evidence'),
                     'picture_verdict': review.get('verdict', '未审核'),
                     'picture_evidence': review.get('evidence'), 'picture_evidence_status': review_status,
                     'original_audio_file': audio.get('file'), 'original_audio_path_status': audio_status,
                     'audio_sha256_from_record': audio.get('sha256'),
                     'audio_verdict': audio_review.get('verdict', '未审核'),
                     'audio_evidence': audio_review.get('evidence'),
                     'pending_attempts': unresolved, 'next_action': next_action,
                     'desktop_needed_by_record': desktop})
    result = {'record': str(record), 'record_sha256': hashlib.sha256(raw).hexdigest(),
              'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'generation_policy': data.get('generation_policy'),
              'delivery_layout': data.get('delivery_layout'), 'rows': rows,
              'unresolved_attempts': len(pending), 'submitted_tasks': len(tasks),
              'limit': 'Declared record and exact path existence only; no UI, source-content review, new permission, or task-state mutation.'}
    lines = ['# 续跑卡（只读记录快照）', '', f'记录SHA256：`{result["record_sha256"]}`', '',
             '先读最新用户指令；此卡不证明当前UI或授予付费权限。只读卡片所指向的缺失阶段证据，已完成分析/上传/审核不重做。', '',
             '| 款色 | 阶段/节点 | 画面 | 原音 | 下一步 |', '| --- | --- | --- | --- | --- |']
    for row in rows:
        lines.append('| ' + ' | '.join(clean(x) for x in [row['product'],
                     str(row['stage'])+'/'+str(row['node_id']),row['picture_verdict'],
                     row['audio_verdict'],row['next_action']])+' |')
    policy = result.get('generation_policy') or {}
    lines += ['', '当前1080剩余名单：'+clean(policy.get('allowed_1080_products_remaining')),
              '当前首次剩余名单：'+clean(policy.get('allowed_first_colors_remaining')),
              '额外重试许可：'+clean(policy.get('additional_retries_allowed')),
              '最新政策原话：'+clean(policy.get('user_text')), '',
              '完整路径和状态见同目录resume.json；有矛盾才展开主记录和对应证据。重新生成卡片会重读主记录，不修改主记录。']
    return raw, result, '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--exclude-dir', action='append', default=[])
    args = parser.parse_args()
    try:
        record = Path(args.record).expanduser().resolve(strict=True)
        out = Path(args.out).expanduser().resolve()
        excluded = [Path(p).expanduser().resolve() for p in args.exclude_dir]
        if out == record.parent or out == record or any(out == p or p in out.parents for p in excluded):
            raise ValueError('Use a dedicated output directory outside excluded paths')
        raw, result, markdown = build(record, excluded)
        out.mkdir(parents=True, exist_ok=True)
        payloads = {'resume.json': json.dumps(result,ensure_ascii=False,indent=2)+'\n', '续跑卡.md': markdown}
        for name, contents in payloads.items():
            if record.read_bytes() != raw:
                raise ValueError('Record advanced; rerun card generation')
            target = out / name
            temp = out / ('.'+uuid.uuid4().hex+'.partial')
            try:
                with temp.open('x',encoding='utf-8',newline='\n') as handle:
                    handle.write(contents)
                if record.read_bytes() != raw:
                    raise ValueError('Record advanced; rerun card generation')
                os.replace(temp, target)
            finally:
                if temp.exists():
                    temp.unlink()
        print(json.dumps({'out':str(out),'record_sha256':result['record_sha256'],
                          'rows':len(result['rows']),'unresolved_attempts':result['unresolved_attempts']},ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc),file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
