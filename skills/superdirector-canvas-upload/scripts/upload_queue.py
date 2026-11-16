"""Plan only missing canvas uploads from exact manifest paths; never operates the UI.

Signatures use path, byte size and mtime_ns, not content hashing. A verified
receipt requires explicit UI evidence supplied by the operator. Unknown upload
state is held for inspection and is never silently re-uploaded.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

MAX_SELECTION_UNITS = 30000
STATUSES = {'verified', 'pending', 'unknown'}
EXTENSIONS = {'image': {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'},
              'video': {'.mp4', '.mov', '.m4v', '.webm', '.mkv', '.avi'}}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def canonical(path):
    return os.path.normcase(str(Path(path).expanduser().resolve()))


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def state_lock(state):
    lock = state.with_name(state.name + '.lock')
    state.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = lock.open('x', encoding='utf-8')
    except FileExistsError as exc:
        raise ValueError(f'State is locked by another writer. Inspect before removing a stale lock: {lock}') from exc
    try:
        with handle:
            handle.write(encode({'pid': os.getpid(), 'started_at': now()}))
        yield
    finally:
        lock.unlink(missing_ok=True)


def is_excluded(path, exclusions):
    return any(path == root or root in path.parents for root in exclusions)


def inventory(manifest, exclusions):
    data = load_json(manifest)
    if not isinstance(data, dict) or not isinstance(data.get('files'), list) or not data['files']:
        raise ValueError('Manifest must have a nonempty files array of exact paths.')
    result, excluded, seen = [], [], {}
    for index, item in enumerate(data['files']):
        if not isinstance(item, dict) or item.get('kind') not in ('video', 'image'):
            raise ValueError(f'Manifest item {index} needs kind video or image.')
        value = item.get('path')
        if not isinstance(value, str) or not value or not Path(value).expanduser().is_absolute():
            raise ValueError(f'Manifest item {index} needs an absolute file path.')
        path = Path(value).expanduser().resolve()
        key = canonical(path)
        if key in seen:
            if seen[key] != item['kind']:
                raise ValueError(f'Duplicate path has conflicting kind: {path}')
            raise ValueError(f'Duplicate exact file path makes the manifest ambiguous: {path}')
        seen[key] = item['kind']
        if item.get('name') is not None and item['name'] != path.name:
            raise ValueError(f'Manifest name differs from the exact path: {path}')
        if path.suffix.lower() not in EXTENSIONS[item['kind']]:
            raise ValueError(f'Manifest kind does not match a recognized media extension: {path}')
        if is_excluded(path, exclusions):
            excluded.append(str(path))
            continue
        if not path.is_file():
            raise ValueError(f'Manifest path is missing or is not a file: {path}')
        stat = path.stat()
        if stat.st_size < 1:
            raise ValueError(f'Empty media file: {path}')
        signature = {'path': str(path), 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
        result.append({'key': key, 'path': str(path), 'name': path.name,
                       'kind': item['kind'], 'directory': str(path.parent),
                       'signature': signature})
    return result, excluded


def read_state(path, manifest, canvas, task_key):
    scope = {'canvas': canvas, 'task_key': task_key}
    if not all(isinstance(x, str) and x.strip() and x == x.strip() for x in scope.values()):
        raise ValueError('Supply exact nonempty --canvas and --task-key identities without surrounding whitespace.')
    if not path.exists():
        return {'version': 2, 'manifest': str(manifest), 'scope': scope, 'signature_mode': 'path+bytes+mtime_ns; no content hash', 'entries': {}}
    data = load_json(path)
    if data.get('version') != 2 or not isinstance(data.get('entries'), dict):
        raise ValueError('Unscoped or unrecognized upload state; choose a new state path, do not reuse old-group receipts.')
    if data.get('scope') != scope:
        raise ValueError('State belongs to another canvas or independent task group. Use a new state path and new material copies.')
    if canonical(data.get('manifest', '')) != canonical(manifest):
        raise ValueError('State belongs to a different manifest. Use its original manifest or a new state path.')
    for entry in data['entries'].values():
        if not isinstance(entry, dict) or entry.get('status') not in STATUSES:
            raise ValueError('Invalid upload receipt status in state.')
    return data


def synchronize(state, items):
    changed = []
    for item in items:
        old = state['entries'].get(item['key'])
        if old and old.get('signature') == item['signature']:
            continue
        next_status = 'unknown' if old and old.get('status') == 'unknown' else 'pending'
        entry = {'path': item['path'], 'kind': item['kind'], 'signature': item['signature'],
                 'status': next_status, 'evidence': None, 'node_id': None, 'updated_at': now()}
        if old:
            entry['previous_receipt'] = {k: old.get(k) for k in ('status', 'signature', 'evidence', 'node_id', 'updated_at')}
            changed.append({'path': item['path'], 'previous_status': old['status'], 'new_status': next_status})
        state['entries'][item['key']] = entry
    return changed


def token(path):
    if any(char in path for char in ('"', '\x00', '\n', '\r')):
        raise ValueError('File selection cannot contain quotes, NUL or newlines.')
    return '"' + path.replace('/', '\\') + '"'


def selection_units(value):
    return len(value.encode('utf-16-le')) // 2


def make_batches(items, size):
    groups = {}
    for kind in ('video', 'image'):
        for item in items:
            if item['kind'] == kind:
                groups.setdefault((kind, item['directory']), []).append(item)
    batches = []
    for (kind, directory), group in groups.items():
        current = []
        for item in group:
            single = token(item['path'])
            if selection_units(single) > MAX_SELECTION_UNITS:
                raise ValueError(f'Single selection path exceeds {MAX_SELECTION_UNITS} UTF-16 units: {item["path"]}')
            candidate = current + [item]
            absolute = ' '.join(token(entry['path']) for entry in candidate)
            if current and (len(candidate) > size or selection_units(absolute) > MAX_SELECTION_UNITS):
                batches.append({'kind': kind, 'directory': directory, 'files': current})
                current = [item]
            else:
                current = candidate
        if current:
            batches.append({'kind': kind, 'directory': directory, 'files': current})
    return batches


def save_text_once(path, text):
    if path.exists():
        if path.read_text(encoding='utf-8') != text:
            raise ValueError(f'Plan artifact changed; refusing to overwrite: {path}')
    else:
        path.write_text(text, encoding='utf-8')


def plan(args):
    manifest = Path(args.manifest).expanduser().resolve(strict=True)
    state_path = Path(args.state).expanduser().resolve()
    exclusions = [Path(p).expanduser().resolve() for p in args.exclude_dir]
    items, excluded = inventory(manifest, exclusions)
    with state_lock(state_path):
        state = read_state(state_path, manifest, args.canvas, args.task_key)
        synchronize(state, items)
        changed = [{'path': item['path'],
                    'previous_status': state['entries'][item['key']]['previous_receipt']['status'],
                    'new_status': state['entries'][item['key']]['status']} for item in items
                   if state['entries'][item['key']]['status'] in ('pending', 'unknown')
                   and state['entries'][item['key']].get('previous_receipt')]
        pending, held, verified = [], [], []
        for item in items:
            status = state['entries'][item['key']]['status']
            {'pending': pending, 'unknown': held, 'verified': verified}[status].append(item)
        batches = make_batches(pending, args.batch_size)
        identity = {'manifest': str(manifest), 'scope': state['scope'], 'batch_size': args.batch_size,
                    'items': [{'signature': item['signature'], 'kind': item['kind'],
                               'status': state['entries'][item['key']]['status']} for item in items],
                    'excluded': excluded, 'changed_inputs': changed}
        plan_id = digest(identity)
        out = Path(args.out).expanduser().resolve() / ('plan-' + plan_id[:16])
        out.mkdir(parents=True, exist_ok=True)
        published = []
        for number, batch in enumerate(batches, 1):
            stem = f'{number:02}-{batch["kind"]}'
            absolute_file, short_file = out / (stem + '-absolute.txt'), out / (stem + '-short.txt')
            save_text_once(absolute_file, ' '.join(token(item['path']) for item in batch['files']))
            save_text_once(short_file, ' '.join(token(item['name']) for item in batch['files']))
            published.append({'number': number, 'kind': batch['kind'], 'directory': batch['directory'],
                              'files': [item['path'] for item in batch['files']],
                              'selection_file': str(absolute_file), 'short_selection_file': str(short_file)})
        result = {'version': 2, 'plan_id': plan_id, 'identity': identity,
                  'signature_mode': state['signature_mode'], 'state_file': str(state_path),
                  'counts': {'pending': len(pending), 'verified': len(verified), 'held_unknown': len(held), 'excluded': len(excluded)},
                  'batches': published, 'next_batch': published[0] if published else None,
                  'holds': [{'path': x['path'], 'reason': 'Upload acceptance is unknown. Inspect the same UI task before any retry.'} for x in held],
                  'changed_inputs': changed, 'excluded_files': excluded,
                  'verification_boundary': 'Explicit UI evidence only. File-stat signatures are not a content-hash guarantee. This tool does not upload or verify cloud persistence.'}
        plan_file = out / 'plan.json'
        save_text_once(plan_file, json.dumps(result, ensure_ascii=False, indent=2))
        lines = ['# 上传差量队列', '', f'画布：{args.canvas}；独立任务组：{args.task_key}', '', f'待传 {len(pending)}；已核 {len(verified)}；受理未知暂停 {len(held)}；排除 {len(excluded)}。', '',
                 '只操作next_batch，核实该批节点后逐个mark verified，再重新plan。unknown不进入上传批次。',
                 '同名跨目录不合批；短文件名仅在已确认文件框目录后使用；绝对路径文本使用Windows反斜杠。', '',
                 f'下一批：{published[0]["selection_file"] if published else "无待传批次"}', '', '## 待核项']
        lines += [f'- {x["path"]}' for x in held] or ['- 无']
        lines += ['', '## 文件变化（旧收据不再复用，受理未知仍暂停）'] + ([f'- {x["path"]}: {x["previous_status"]} → {x["new_status"]}' for x in changed] or ['- 无'])
        lines += ['', '签名仅path+bytes+mtime_ns，不重新读取媒体内容；不能检测保留大小和mtime的内容篡改。']
        save_text_once(out / 'queue.md', '\n'.join(lines) + '\n')
        state['updated_at'] = now()
        atomic_json(state_path, state)
    return {'plan': str(plan_file), 'queue': str(out / 'queue.md'), 'counts': result['counts'], 'batches': len(published), 'next_batch': result['next_batch']}


def mark(args):
    manifest = Path(args.manifest).expanduser().resolve(strict=True)
    state_path = Path(args.state).expanduser().resolve()
    exclusions = [Path(p).expanduser().resolve() for p in args.exclude_dir]
    items, _ = inventory(manifest, exclusions)
    target = canonical(args.file)
    matches = [item for item in items if item['key'] == target]
    if len(matches) != 1:
        raise ValueError('--file must identify one exact non-excluded manifest file.')
    if not args.evidence or not args.evidence.strip():
        raise ValueError('--evidence must describe the actual observation, not just a successful tool call.')
    with state_lock(state_path):
        state = read_state(state_path, manifest, args.canvas, args.task_key)
        synchronize(state, items)
        item = matches[0]
        entry = state['entries'][target]
        history = entry.get('history', [])
        history.append({k: entry.get(k) for k in ('status', 'evidence', 'node_id', 'updated_at')})
        entry.update({'status': args.status, 'evidence': args.evidence.strip(),
                      'node_id': args.node_id, 'updated_at': now(), 'history': history})
        state['updated_at'] = now()
        atomic_json(state_path, state)
    return {'path': item['path'], 'status': args.status, 'state': str(state_path), 'ui_verified_by_tool': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'mark'):
        command = sub.add_parser(name)
        command.add_argument('--manifest', required=True)
        command.add_argument('--state', required=True)
        command.add_argument('--canvas', required=True, help='Exact observed canvas name; receipts never cross canvases')
        command.add_argument('--task-key', required=True, help='Independent new task group identity, e.g. sourceId-product; new group needs a new state')
        command.add_argument('--exclude-dir', action='append', default=[])
        if name == 'plan':
            command.add_argument('--out', required=True)
            command.add_argument('--batch-size', type=int, default=5)
        else:
            command.add_argument('--file', required=True)
            command.add_argument('--status', required=True, choices=sorted(STATUSES))
            command.add_argument('--evidence', required=True)
            command.add_argument('--node-id')
    args = parser.parse_args()
    if args.command == 'plan' and args.batch_size < 1:
        parser.error('--batch-size must be positive; 5 is conservative, not an application limit.')
    try:
        result = plan(args) if args.command == 'plan' else mark(args)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
