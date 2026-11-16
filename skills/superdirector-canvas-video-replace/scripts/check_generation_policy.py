"""Read-only record-policy check; never authorizes or submits generation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


STAGES = ('480', '1080', 'other')


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def identity_fields(item, *, attempt=False):
    if not isinstance(item, dict) or item.get('stage') not in STAGES:
        raise ValueError('Every task/attempt needs a supported string stage')
    for field in ('product', 'task_id', 'node_id', 'color'):
        if item.get(field) is not None and not nonempty(item[field]):
            raise ValueError(field + ' must be a non-empty string or null')
    if not attempt and type(item.get('submitted')) is not bool:
        raise ValueError('Every task needs boolean submitted')
    if attempt or item['submitted']:
        if nonempty(item.get('task_id')):
            return ('task', item['task_id'])
        time_value = (item.get('attempted_at') or item.get('submitted_at')) if attempt else item.get('submitted_at')
        if not nonempty(item.get('node_id')) or not nonempty(time_value):
            raise ValueError('Submitted task/attempt needs task_id or node_id plus timestamp')
        parsed = datetime.fromisoformat(time_value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('Task/attempt timestamp needs an explicit timezone')
        return ('node', item['node_id'], time_value)
    return None


def _check(data, product, color, stage):
    reasons = []
    if not isinstance(data, dict) or not isinstance(data.get('tasks'), list):
        raise ValueError('Record needs a tasks list')
    if not nonempty(product) or (color is not None and not nonempty(color)) or stage not in STAGES:
        raise ValueError('Target needs exact product/color and supported string stage')
    identity = data.get('identity') or {}
    if not isinstance(identity, dict):
        raise ValueError('identity must be an object')
    attempts = data.get('pending_attempts') or []
    if not isinstance(attempts, list):
        raise ValueError('pending_attempts must be a list')
    keys = []
    for item in data['tasks']:
        key = identity_fields(item)
        if key is not None:
            keys.append(key)
    if len(keys) != len(set(keys)):
        raise ValueError('Submitted task identity is duplicated or ambiguous')
    for item in attempts:
        identity_fields(item, attempt=True)
        if item.get('acceptance') is not None and not nonempty(item['acceptance']):
            raise ValueError('Attempt acceptance must be a non-empty string or null')
    policy = data.get('generation_policy')
    if not isinstance(policy, dict):
        return {'record_policy_permits': None, 'reasons': ['任务未记录generation_policy，需核最新用户授权与限制。']}
    if policy.get('deduplicate_by') not in (['product', 'color'], ['product']):
        return {'record_policy_permits': None, 'reasons': ['不支持或未明确的去重字段；不得猜测政策。']}
    for field in ('new_1080_submissions_allowed', 'additional_retries_allowed',
                  'existing_tasks_follow_download_review_audio_archive_only'):
        if field not in policy:
            return {'record_policy_permits': None, 'reasons': ['任务政策缺少关键字段' + field + '，需核最新授权，不能默认为允许。']}
        if type(policy[field]) is not bool:
            raise ValueError(field + ' must be boolean')
    allowed = policy.get('allowed_first_colors_remaining')
    if allowed is not None and (not isinstance(allowed, list) or not all(nonempty(value) for value in allowed)):
        raise ValueError('allowed_first_colors_remaining must be a non-empty string list')
    by_color = policy['deduplicate_by'] == ['product', 'color']
    target = (product, color if by_color else None)
    colors = data.get('colors') or []
    if not isinstance(colors, list) or any(not isinstance(item, dict) for item in colors):
        raise ValueError('colors must be an object list')
    catalog = [*data['tasks'], *colors]
    known = {(item.get('product'), item.get('color') if by_color else None)
             for item in catalog if isinstance(item, dict) and item.get('product')}
    known.update((value, None) for value in allowed or [])
    if not known and identity.get('product'):
        known.add((identity['product'], None))
    if target not in known:
        return {'record_policy_permits': None,
                'reasons': ['商品/颜色字段格式未与主记录精确匹配；先核同款色，不能用改名或拆分字段绕过去重。']}

    def same(item):
        if not isinstance(item, dict):
            raise ValueError('Task/attempt must be an object')
        item_product = item.get('product') or identity.get('product')
        if not isinstance(item_product, str) or not item_product:
            raise ValueError('Task/attempt product is unknown')
        return (item_product, item.get('color') if by_color else None) == target

    tasks = []
    for item in data['tasks']:
        if not isinstance(item, dict) or type(item.get('submitted')) is not bool:
            raise ValueError('Every task needs boolean submitted')
        if same(item) and item['submitted']:
            tasks.append(item)
    unresolved = []
    for item in attempts:
        if not same(item):
            continue
        acceptance = item.get('acceptance') or 'unknown'
        if isinstance(acceptance, str) and acceptance.startswith('resolved_'):
            linked = [task for task in tasks if task.get('stage') == item.get('stage') and
                      ((item.get('task_id') and task.get('task_id') == item['task_id']) or
                       (item.get('node_id') and task.get('node_id') == item['node_id']))]
            if len(linked) != 1:
                unresolved.append(item)
        else:
            unresolved.append(item)
    if unresolved:
        reasons.append('存在受理未知或无法唯一关联已解决记录的尝试，先追查原任务，不重按生成。')
    if tasks and policy.get('existing_tasks_follow_download_review_audio_archive_only') is True:
        reasons.append('该款色已有提交；当前政策只允许跟进、下载、审核、合音和归档。')
    if stage == '1080' and policy.get('new_1080_submissions_allowed') is False:
        reasons.append('当前任务禁止新1080提交。')
    if any(task.get('stage') == stage for task in tasks) and policy.get('additional_retries_allowed') is False:
        reasons.append('该款色该阶段已有提交；当前任务禁止额外重试。')
    if not tasks and not unresolved:
        if allowed is None:
            return {'record_policy_permits': None, 'reasons': ['未明确允许首次生成的范围，需核最新任务授权。']}
        if product not in allowed:
            reasons.append('该款色未列入当前允许首次生成的范围。')
    return {'record_policy_permits': not reasons, 'reasons': reasons,
            'submitted_matches': len(tasks), 'unresolved_attempt_matches': len(unresolved),
            'policy_updated_at': policy.get('updated_at'),
            'scope': '仅按记录中的精确商品/颜色字段检查任务政策；不同字段格式须人工先核同款色，不做名称拆分或别名猜测。',
            'next': '仍须核最新用户指令、当前UI、参数、审核门槛及单一操作者；此结果不授予付费权限。'}


def check(data, product, color, stage):
    try:
        result = _check(data, product, color, stage)
    except (ValueError, TypeError, KeyError) as exc:
        result = {'record_policy_permits': None, 'reasons': ['记录或身份字段需核实：' + str(exc)]}
    result['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', required=True)
    parser.add_argument('--product', required=True, help='Exact record identifier; do not rename to evade deduplication')
    parser.add_argument('--color', help='Exact separate color field; omit for legacy combined product identifiers')
    parser.add_argument('--stage', required=True, choices=('480', '1080', 'other'))
    args = parser.parse_args()
    try:
        path = Path(args.record).expanduser().resolve()
        raw = path.read_bytes()
        read_at = datetime.now(timezone.utc).isoformat()
        result = check(json.loads(raw.decode('utf-8-sig')), args.product, args.color, args.stage)
        result['record'] = str(path)
        result['record_sha256'] = hashlib.sha256(raw).hexdigest()
        result['record_read_at_utc'] = read_at
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result['record_policy_permits'] is True else 2 if result['record_policy_permits'] is False else 3
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'error': str(exc), 'record_policy_permits': None}, ensure_ascii=False), file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
