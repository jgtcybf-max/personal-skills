"""Build an upload inventory and absolute/short-name Open-dialog selections. No uploads."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.m4v', '.webm', '.mkv', '.avi'}


def collect(values: list[str], extensions: set[str], recursive: bool) -> list[Path]:
    found: list[Path] = []
    for value in values:
        path = Path(value).expanduser().resolve(strict=True)
        candidates = (path.rglob('*') if recursive else path.iterdir()) if path.is_dir() else [path]
        selected = sorted(
            (p for p in candidates if p.is_file() and p.suffix.lower() in extensions),
            key=lambda p: str(p).casefold(),
        )
        if not selected:
            raise ValueError(f'No matching media in: {path}')
        found.extend(selected)
    return list(dict.fromkeys(found))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', action='append', default=[], help='One video file or an unambiguous video directory')
    parser.add_argument('--images', action='append', default=[], help='One image file or image directory')
    parser.add_argument('--recursive', action='store_true')
    parser.add_argument('--batch-size', type=int, default=5)
    parser.add_argument('--manifest', required=True)
    args = parser.parse_args()
    if not args.video and not args.images:
        parser.error('Supply --video and/or --images')
    if args.batch_size < 1:
        parser.error('--batch-size must be positive')
    try:
        videos = collect(args.video, VIDEO_EXTENSIONS, args.recursive)
        images = collect(args.images, IMAGE_EXTENSIONS, args.recursive)
        if len(videos) > 1 and any(Path(p).is_dir() for p in args.video):
            raise ValueError('Multiple videos found. Select explicit video files with repeated --video arguments.')
        manifest = Path(args.manifest).expanduser().resolve()
        files = [
            {'path': str(p), 'name': p.name, 'kind': kind, 'bytes': p.stat().st_size}
            for kind, paths in [('video', videos), ('image', images)] for p in paths
        ]
        if any(item['bytes'] == 0 for item in files):
            raise ValueError('Empty media file in selection')
        batches = []
        for kind in ('video', 'image'):
            # Short-name selection is valid only after navigating to its paired
            # directory. Never mix parents, including identically named files.
            directories: dict[Path, list[dict]] = {}
            for item in files:
                if item['kind'] == kind:
                    directories.setdefault(Path(item['path']).parent, []).append(item)
            batch_number = 0
            for directory, group in directories.items():
                for index in range(0, len(group), args.batch_size):
                    batch_number += 1
                    batch = group[index:index + args.batch_size]
                    stem = f'{manifest.stem}-selection-{kind}-{batch_number:02}'
                    selection = manifest.parent / f'{stem}.txt'
                    short_selection = manifest.parent / f'{stem}-short.txt'
                    batches.append({
                        'kind': kind,
                        'directory': str(directory),
                        'files': [item['path'] for item in batch],
                        'selection_file': str(selection),
                        'short_selection_file': str(short_selection),
                    })
        targets = [manifest] + [
            Path(batch[key]) for batch in batches
            for key in ('selection_file', 'short_selection_file')
        ]
        if any(p.exists() for p in targets):
            raise FileExistsError('Output already exists; reuse the inventory or choose a new manifest path')
        manifest.parent.mkdir(parents=True, exist_ok=True)
        for batch in batches:
            selection_text = ' '.join('"' + path + '"' for path in batch['files'])
            short_text = ' '.join('"' + Path(path).name + '"' for path in batch['files'])
            with Path(batch['selection_file']).open('x', encoding='utf-8') as handle:
                handle.write(selection_text)
            with Path(batch['short_selection_file']).open('x', encoding='utf-8') as handle:
                handle.write(short_text)
        data = {'canvas': None, 'files': files, 'counts': {'video': len(videos), 'image': len(images)}, 'batches': batches}
        with manifest.open('x', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        print(json.dumps({'manifest': str(manifest), 'counts': data['counts'], 'batches': len(batches)}, ensure_ascii=False))
    except (OSError, ValueError) as error:
        parser.exit(2, f'{error}\n')


if __name__ == '__main__':
    main()
