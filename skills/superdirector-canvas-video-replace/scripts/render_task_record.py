"""Render progress, compute ledger and delivery summary from one local record.

This prepares reports only. It never submits, generates, edits media or approves quality.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys

VERDICTS = {'通过', '有瑕疵', '不通过', '未审核'}


def amount(value, field):
    if value is None:
        return None
    try:
        if isinstance(value, bool):
            raise InvalidOperation
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError):
        raise ValueError(field + ' must be a nonnegative finite number or null') from None


def text(value):
    return str(value).replace('|', '\\|').replace('\r', ' ').replace('\n', ' ') if value is not None else '待核实'


def points(value):
    return format(value, 'f') if value is not None else '待核实'


def local_file(value, root):
    if not isinstance(value, str) or not value:
        return None
    path = Path(value).expanduser()
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    return path if path.is_file() else None


def verdict(value, field):
    if value is None:
        return {'verdict': '未审核'}
    if not isinstance(value, dict) or value.get('verdict', '未审核') not in VERDICTS:
        raise ValueError(field + ' must contain a supported verdict')
    return value


def resolve_parent480(task, tasks, identity):
    """Resolve declared parent without inventing an ID or guessing reused nodes."""
    explicit = task.get('parent480_key')
    if explicit:
        candidates = [parent for parent in tasks if parent['key'] == explicit]
    else:
        reference = task.get('parent480')
        candidates = [parent for parent in tasks if reference and parent.get('task_id') == reference]
        if not candidates:
            candidates = [parent for parent in tasks if reference and parent.get('node_id') == reference
                          and parent['submitted'] and parent['stage'] == '480']
    if len(candidates) != 1:
        return None
    parent = candidates[0]
    parent_product = parent.get('product') or identity['product']
    task_product = task.get('product') or identity['product']
    if parent_product != task_product or parent.get('color') != task.get('color'):
        return None
    return parent


def normalize(data, root):
    if not isinstance(data, dict) or not isinstance(data.get('identity'), dict):
        raise ValueError('identity object is required')
    identity = data['identity']
    for key in ('source_video', 'product', 'canvas'):
        if not isinstance(identity.get(key), str) or not identity[key].strip():
            raise ValueError('identity.' + key + ' is required')
    if not isinstance(data.get('tasks'), list):
        raise ValueError('tasks must be a list')
    seen, tasks, warnings = set(), [], []
    for index, value in enumerate(data['tasks'], 1):
        if not isinstance(value, dict) or type(value.get('submitted')) is not bool:
            raise ValueError(f'task {index} needs a boolean submitted')
        if value.get('stage') not in ('480', '1080', 'other'):
            raise ValueError(f'task {index} stage must be 480, 1080 or other')
        task_id = value.get('task_id')
        fallback = (value.get('node_id'), value.get('submitted_at'))
        if task_id and not isinstance(task_id, str):
            raise ValueError('task_id must be a string')
        if task_id:
            key = 'task:' + task_id
        elif all(isinstance(x, str) and x.strip() for x in fallback):
            key = 'node:' + '|'.join(fallback)
        elif value['submitted']:
            raise ValueError(f'submitted task {index} needs task_id or node_id + submitted_at')
        else:
            key = f'draft:{index}'
        if key in seen:
            raise ValueError('Duplicate task identity: ' + key)
        seen.add(key)
        task = {**value, 'key': key, 'review': verdict(value.get('review'), key + '.review')}
        task['file_exists'] = local_file(task.get('file'), root) is not None
        for field in ('expected_points', 'debit', 'refund'):
            task[field] = amount(value.get(field), key + '.' + field)
        evidence, verified = value.get('cost_evidence') or {}, value.get('cost_verified') or {}
        if not isinstance(evidence, dict) or not isinstance(verified, dict):
            raise ValueError('cost_evidence and cost_verified must be objects')
        for field in ('debit', 'refund'):
            task[field + '_verified'] = (verified.get(field) is True and task[field] is not None
                                         and local_file(evidence.get(field), root) is not None)
        task['review_evidence_exists'] = local_file(task['review'].get('evidence'), root) is not None
        if value.get('audio') is not None:
            if not isinstance(value['audio'], dict):
                raise ValueError(key + '.audio must be an object')
            audio_review = value['audio'].get('review') or {'verdict': '未审核'}
            if not isinstance(audio_review, dict) or not isinstance(audio_review.get('verdict', '未审核'), str):
                raise ValueError(key + '.audio.review needs a string verdict')
            task['audio'] = {**value['audio'], 'review': audio_review}
        tasks.append(task)
    for task in tasks:
        if task['submitted'] and task['stage'] == '1080':
            parent = resolve_parent480(task, tasks, identity)
            if not (parent and parent['submitted'] and parent['stage'] == '480'
                    and parent['review'].get('verdict') == '通过' and parent['review_evidence_exists']):
                warnings.append(task['key'] + '：未找到有审核证据的已通过480父任务；保留实际历史，不能称合规正式版。')
    audio = data.get('audio') or {}
    if not isinstance(audio, dict):
        raise ValueError('audio must be an object')
    audio = {**audio, 'review': verdict(audio.get('review'), 'audio.review')}
    return identity, tasks, warnings, audio


def summary_for(tasks, warnings):
    submitted = [t for t in tasks if t['submitted']]
    expected_known = [t['expected_points'] for t in submitted if t['expected_points'] is not None]
    debit = sum((t['debit'] for t in submitted if t['debit_verified']), Decimal(0))
    refund = sum((t['refund'] for t in submitted if t['refund_verified']), Decimal(0))
    pending = sum(not (t['debit_verified'] and t['refund_verified']) for t in submitted)
    return {'submitted_tasks': len(submitted), 'drafts': len(tasks)-len(submitted),
            'submitted_expected_known_subtotal': points(sum(expected_known, Decimal(0))),
            'submitted_expected_unknown_tasks': len(submitted)-len(expected_known),
            'verified_debit_subtotal': points(debit), 'verified_refund_subtotal': points(refund),
            'verified_net_subtotal': points(debit-refund),
            'project_net_total': None if pending else points(debit-refund),
            'pending_cost_tasks': pending, 'warnings': warnings,
            'scope': 'Declared record and evidence-file existence only; no semantic proof or platform verification.'}


def render(record, output):
    data = json.loads(record.read_text(encoding='utf-8-sig'))
    identity, tasks, warnings, audio = normalize(data, record.parent)
    summary = summary_for(tasks, warnings)
    if output.exists():
        raise ValueError('Output must be a new directory; previous reports are never overwritten')
    stamp = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    head = f"- 商品：{text(identity['product'])}\n- 画布：{text(identity['canvas'])}\n- 原视频：{text(identity['source_video'])}\n- 记录来源：{record}\n- 生成报告时间（北京时间）：{stamp}\n"
    costs = (f"已提交{summary['submitted_tasks']}笔；草案{summary['drafts']}笔。\n"
             f"已提交预计已知小计{summary['submitted_expected_known_subtotal']}点；预计未知{summary['submitted_expected_unknown_tasks']}笔。\n"
             f"已核实实扣小计{summary['verified_debit_subtotal']}点；退款小计{summary['verified_refund_subtotal']}点；净额小计{summary['verified_net_subtotal']}点。\n"
             f"本项目净实际总额：{summary['project_net_total'] if summary['project_net_total'] is not None else '未确认'}；费用待核实{summary['pending_cost_tasks']}笔。\n")
    disclaimer = '\n本工具只整理填写的记录并检查证据文件存在，不读取平台账单、不判断画面或声音、不提交生成。声明通过仍需执行者审看；文件存在不等于审核通过。\n'
    rows = ['| 任务标识 | 提交时间 | 阶段 | 状态 | 实际设置/模型/数量 | 预计 | 实扣 | 退款 | 净额 | 费用证据 |',
            '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    progress = ['| 任务标识 | 阶段 | 已提交 | 记录审核结论 | 审核证据 | 成片文件 |', '| --- | --- | --- | --- | --- | --- |']
    for task in tasks:
        net = task['debit'] - task['refund'] if task['debit_verified'] and task['refund_verified'] else None
        actual = '/'.join(text(task.get(k)) for k in ('setting', 'model', 'quantity'))
        evidence = task.get('cost_evidence') or {}
        rows.append('| ' + ' | '.join([text(task['key']), text(task.get('submitted_at')), task['stage'], '已提交' if task['submitted'] else '草案（不计提交合计）', actual,
                    points(task['expected_points']), points(task['debit']) + ('（已核实）' if task['debit_verified'] else '（未核实）'),
                    points(task['refund']) + ('（已核实）' if task['refund_verified'] else '（未核实）'), points(net), text(evidence)]) + ' |')
        progress.append('| ' + ' | '.join([text(task['key']), task['stage'], str(task['submitted']), task['review'].get('verdict', '未审核'),
                        '文件存在，内容由执行者负责' if task['review_evidence_exists'] else '未核验/文件缺失',
                        text(task.get('file')) + ('（文件存在）' if task['file_exists'] else '（未找到或未提供）')]) + ' |')
    warning_text = '\n'.join('- ' + value for value in warnings) or '- 未发现记录内1080父阶段矛盾；这不证明任务全部完成。'
    audio_path = local_file(audio.get('file'), record.parent)
    audio_note = (f"- 原音来源：{text(audio.get('source'))}\n- 最终原声版：{text(audio.get('file'))}（{'文件存在' if audio_path else '未找到或未提供'}）\n"
                  f"- 配音审核记录：{audio['review'].get('verdict', '未审核')}；证据：{text(audio['review'].get('evidence'))}\n")
    task_audio = [task for task in tasks if isinstance(task.get('audio'), dict)]
    if task_audio:
        audio_rows = ['| 任务标识 | 原音来源 | 本地原声版 | 听审记录 | 听审证据 |',
                      '| --- | --- | --- | --- | --- |']
        for task in task_audio:
            item = task['audio']
            file_exists = local_file(item.get('file'), record.parent) is not None
            review_exists = local_file(item['review'].get('evidence'), record.parent) is not None
            audio_rows.append('| ' + ' | '.join([text(task['key']), text(item.get('source')),
                text(item.get('file')) + ('（文件存在）' if file_exists else '（未找到或未提供）'),
                text(item['review'].get('verdict', '未审核')), text(item['review'].get('evidence'))
                + ('（文件存在，内容由执行者负责）' if review_exists else '（未核验/文件缺失）')]) + ' |')
        audio_note += '\n各任务原音记录（文件存在不代表听审通过）：\n\n' + '\n'.join(audio_rows) + '\n'
    documents = {'执行进度.md': '# 执行进度（记录快照）\n\n' + head + '\n' + '\n'.join(progress) + '\n\n' + warning_text + '\n\n' + audio_note + '\n' + costs + disclaimer,
                 '算力消耗明细.md': '# 算力消耗明细（记录快照）\n\n' + head + '\n' + '\n'.join(rows) + '\n\n' + costs + '\n草案预计不计入已提交合计；未知费用不是0；失败不代表退款。同一任务的下载/副本/本地合音不新增任务。\n' + disclaimer,
                 '交付摘要.md': '# 交付摘要（记录快照）\n\n' + head + '\n' + '\n'.join(progress) + '\n\n' + audio_note + '\n' + warning_text + '\n\n' + costs + disclaimer}
    output.mkdir(parents=True, exist_ok=False)
    for name, body in documents.items():
        with (output/name).open('x', encoding='utf-8') as handle:
            handle.write(body)
    with (output/'summary.json').open('x', encoding='utf-8') as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    return {'output': str(output), **summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', required=True, help='Local task-record.json; relative evidence paths resolve beside it')
    parser.add_argument('--out', required=True, help='New report snapshot directory; no overwrites')
    args = parser.parse_args()
    try:
        result = render(Path(args.record).expanduser().resolve(), Path(args.out).expanduser().resolve())
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
