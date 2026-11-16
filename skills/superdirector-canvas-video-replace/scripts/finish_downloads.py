"""Prepare review evidence and original-audio copies of exact local downloads.

Usage: finish_downloads.py --manifest jobs.json --out NEW_DIR [--reuse] [--jobs 2]
Manifest: {"jobs":[{"key":"shoe-black-1080","product":"...","video":"...",
"original_audio":"...","source_video":"...", "focus":["0:3:0.2"]}]}

No desktop, network, generation, task-record writes, semantic approval or delivery.
Existing input/options/tool signatures must match on --reuse. Intact steps are
reused; missing artifacts are rebuilt, while changed artifacts fail closed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from review_media import focus_range, probe_media, resolve_executable

HERE = Path(__file__).resolve().parent
REVIEW = HERE / 'review_media.py'
SCHEMA = 1
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def signature(path):
    before = path.stat()
    result = {'path': str(path), 'bytes': before.st_size, 'sha256': sha256(path)}
    after = path.stat()
    if not path.is_file() or before.st_size <= 0:
        raise ValueError('Input must be a nonempty file: ' + str(path))
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Input changed while hashing: ' + str(path))
    return result


def utc():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, data):
    temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.partial')
    with temp.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


@contextmanager
def output_lock(output):
    lock = output / '.finish-downloads.lock'
    try:
        with lock.open('x', encoding='utf-8') as handle:
            handle.write(json.dumps({'pid': os.getpid(), 'started_utc': utc()}))
    except FileExistsError:
        raise ValueError('Output is locked. Verify no prior process is running before removing its lock.') from None
    try:
        yield
    finally:
        lock.unlink()


def command(args, label, timeout=300):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout,
                                creationflags=FLAGS)
    except subprocess.TimeoutExpired:
        raise RuntimeError(label+' exceeded local timeout; inspect partial output') from None
    if result.returncode:
        # Raw FFmpeg diagnostics can contain unrelated metadata. Keep them private.
        raise RuntimeError(label+f' failed (exit {result.returncode}); no automatic codec or timing changes')
    return result.stdout


def stream_hash(ffmpeg, path, stream):
    return command([ffmpeg, '-v', 'error', '-nostdin', '-i', str(path), '-map', stream,
                    '-c', 'copy', '-f', 'streamhash', '-hash', 'sha256', '-'],
                   'Compressed stream verification').decode('ascii').strip()


def artifact_record(folder, path):
    return {'relative_path': path.relative_to(folder).as_posix(),
            'bytes': path.stat().st_size, 'sha256': sha256(path)}


def check_artifacts(folder, records):
    missing = []
    for item in records:
        path = folder / item['relative_path']
        if not path.is_file():
            missing.append(item['relative_path'])
        elif path.stat().st_size != item['bytes'] or sha256(path) != item['sha256']:
            raise ValueError('Cached artifact changed; choose a new output directory: '+str(path))
    return missing


def move_missing(source, target):
    """Publish only new files. Recovery never overwrites an existing artifact."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError('Refusing to replace existing artifact: '+str(target))
    os.rename(source, target)


def prepare_job(job, output, ffmpeg, ffprobe):
    started = time.perf_counter()
    folder = output / job['key']
    folder.mkdir(exist_ok=True)
    state_path = folder / 'state.json'
    state = read_json(state_path) if state_path.exists() else {'schema': SCHEMA, 'key': job['key'], 'steps': {}}
    if state.get('inputs_changed_during_prior_run'):
        raise ValueError('Prior input mutation invalidated this job cache; choose a new output folder')
    state['status'] = 'running'
    state['updated_utc'] = utc()
    atomic_json(state_path, state)
    reused, completed = [], []
    video, audio = Path(job['video']), Path(job['original_audio'])
    try:
        review = folder/'review'
        old_review = state['steps'].get('review')
        missing = check_artifacts(folder, old_review['artifacts']) if old_review else None
        if old_review and not missing:
            reused.append('review')
        else:
            # Preserve incomplete attempts; only this tool's signed folder is used.
            staging = folder/('review-'+uuid.uuid4().hex+'.partial')
            args = [sys.executable, '-X', 'utf8', str(REVIEW), '--video', str(video),
                    '--out', str(staging), '--ffmpeg', ffmpeg]
            if ffprobe:
                args += ['--ffprobe', ffprobe]
            for interval in job['focus']:
                args += ['--focus', interval]
            command(args, 'Review evidence preparation')
            meta = read_json(staging/'metadata.json')
            if not meta['input_unchanged_during_inspection'] or meta['all_declared_frames_decoded'] is False:
                raise ValueError('Input changed or declared video frames did not fully decode')
            if not review.exists():
                os.rename(staging, review)
            elif old_review:
                for relative in missing:
                    relative_inside_review = Path(relative).relative_to('review')
                    move_missing(staging/relative_inside_review, folder/relative)
            else:
                # A prior process may have published review/ then exited before
                # the checkpoint. Verify deterministic samples against a fresh
                # signed-input decode; recover the timing-bearing metadata only
                # when its input and decoded frame facts agree.
                expected_names = {p.name for p in staging.iterdir() if p.is_file()}
                actual_names = {p.name for p in review.iterdir() if p.is_file()}
                if actual_names - expected_names:
                    raise ValueError('Untracked review folder contains unexpected files; choose a new output')
                for fresh in staging.iterdir():
                    if not fresh.is_file():continue
                    target = review/fresh.name
                    if not target.exists():
                        move_missing(fresh,target)
                    elif fresh.name == 'metadata.json':
                        prior = read_json(target)
                        fields = ('input_file','input_bytes','width','height','fps','decoded_frames',
                                  'all_declared_frames_decoded','input_unchanged_during_inspection')
                        if any(prior.get(k)!=meta.get(k) for k in fields):
                            raise ValueError('Uncheckpointed review metadata does not match current inputs')
                    elif sha256(target)!=sha256(fresh):
                        raise ValueError('Uncheckpointed review artifact differs; choose a new output')
            artifacts = [artifact_record(folder, p) for p in sorted(review.iterdir()) if p.is_file()]
            state['steps']['review'] = {'completed_utc': utc(), 'artifacts': artifacts}
            atomic_json(state_path, state)
            completed.append('review')

        mux = folder/'prepared_original_audio.mp4'
        mux_step = state['steps'].get('mux')
        mux_missing = check_artifacts(folder, mux_step['artifacts']) if mux_step else None
        if mux_step and not mux_missing:
            reused.append('mux')
        else:
            if not mux.exists():
                partial = folder/('audio-'+uuid.uuid4().hex+'.partial.mp4')
                command([ffmpeg, '-n', '-v', 'error', '-nostdin', '-i', str(video),
                         '-i', str(audio), '-map', '0:v:0', '-map', '1:a:0',
                         '-c:v', 'copy', '-c:a', 'copy', '-movflags', '+faststart', str(partial)],
                        'Original-audio stream-copy mux')
                move_missing(partial, mux)
            # An uncheckpointed mux after interruption is not trusted until verify.
            state['steps']['mux'] = {'completed_utc': utc(), 'artifacts': [artifact_record(folder, mux)]}
            state['steps'].pop('verify', None)
            atomic_json(state_path, state)
            completed.append('mux')

        verify = state['steps'].get('verify')
        if verify and not check_artifacts(folder, verify['artifacts']):
            reused.append('verify')
        else:
            input_video_hash = stream_hash(ffmpeg, video, '0:v:0')
            output_video_hash = stream_hash(ffmpeg, mux, '0:v:0')
            input_audio_hash = stream_hash(ffmpeg, audio, '0:a:0')
            output_audio_hash = stream_hash(ffmpeg, mux, '0:a:0')
            if input_video_hash != output_video_hash or input_audio_hash != output_audio_hash:
                raise ValueError('Mux compressed stream hashes do not match the exact inputs')
            meta = probe_media(mux, ffprobe, ffmpeg, 10)
            video_count = sum(s['type']=='video' for s in meta['streams'])
            audio_count = sum(s['type']=='audio' for s in meta['streams'])
            if video_count != 1 or audio_count != 1:
                raise ValueError('Mux must contain exactly one video and one audio stream')
            command([ffmpeg, '-v', 'error', '-xerror', '-err_detect', 'explode', '-nostdin',
                     '-i', str(mux), '-map', '0:v:0', '-map', '0:a:0', '-f', 'null',
                     'NUL' if os.name=='nt' else '/dev/null'], 'Full audio/video decode')
            evidence = folder/'verification.json'
            verification = {'schema':SCHEMA, 'verified_utc':utc(), 'product':job['product'],
                'video':job['inputs']['video'], 'original_audio':job['inputs']['original_audio'],
                'source_video':job['inputs'].get('source_video'),
                'prepared_original_audio':artifact_record(folder, mux), 'output_metadata':meta,
                'video_compressed_stream_hash':output_video_hash,
                'original_audio_compressed_stream_hash':output_audio_hash,
                'video_stream_copy_equal':True, 'audio_stream_copy_equal':True,
                'video_stream_count':video_count, 'audio_stream_count':audio_count,
                'full_av_decode_passed':True, 'audio_processing':'Explicit first source audio, stream copy; generated audio omitted',
                'video_processing':'Stream copy; no resizing, stretching or reencoding',
                'speed_trim_loop_gain_or_freeze_applied':False,
                'time_alignment_reviewed':False, 'semantic_reviewed':False,
                'listening_reviewed':False, 'target_player_compatibility_confirmed':False,
                'final_verdict':'未审核',
                'scope':'Local technical preparation only. Review original source timing, product/motion and actual audio before acceptance.'}
            atomic_json(evidence, verification)
            state['steps']['verify'] = {'completed_utc':utc(), 'artifacts':[artifact_record(folder,evidence)]}
            atomic_json(state_path,state)
            completed.append('verify')
        # Rehash exact source inputs after every write/long decode before checkpoint.
        for field, before in job['inputs'].items():
            if signature(Path(before['path'])) != before:
                state['inputs_changed_during_prior_run'] = True
                raise ValueError('Input changed during processing: '+field)
        state.update(status='prepared', updated_utc=utc(), reused_steps=reused,
                     performed_steps=completed, last_run_seconds=round(time.perf_counter()-started,4))
        state.pop('error',None)
        atomic_json(state_path,state)
        return {'key':job['key'], 'product':job['product'], 'status':'prepared',
                'review_directory':str(review), 'prepared_original_audio':str(mux),
                'verification':str(folder/'verification.json'),
                'reused_steps':reused,'performed_steps':completed,
                'wall_clock_seconds':state['last_run_seconds'],'final_verdict':'未审核'}
    except Exception as exc:
        state.update(status='failed',updated_utc=utc(),error=str(exc),
                     last_run_seconds=round(time.perf_counter()-started,4))
        atomic_json(state_path,state)
        return {'key':job['key'],'product':job['product'],'status':'failed','error':str(exc),
                'wall_clock_seconds':state['last_run_seconds'],'final_verdict':'未审核'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--reuse',action='store_true')
    parser.add_argument('--jobs',type=int,choices=(1,2),default=2,help='Local workers only; never platform generation count')
    parser.add_argument('--ffmpeg')
    parser.add_argument('--ffprobe')
    args=parser.parse_args()
    started=time.perf_counter()
    try:
        manifest=Path(args.manifest).expanduser().resolve(strict=True)
        data=read_json(manifest)
        if not isinstance(data,dict) or not isinstance(data.get('jobs'),list) or not 1<=len(data['jobs'])<=100:
            raise ValueError('Manifest requires 1 to 100 jobs')
        ffmpeg=resolve_executable(args.ffmpeg,'ffmpeg')
        ffprobe=resolve_executable(args.ffprobe,'ffprobe')
        if not ffmpeg: raise ValueError('FFmpeg was not found')
        tool_version=command([ffmpeg,'-version'],'FFmpeg version',10).decode('utf-8',errors='replace').splitlines()[0]
        probe_version=(command([ffprobe,'-version'],'FFprobe version',10).decode('utf-8',errors='replace').splitlines()[0]
                       if ffprobe else None)
        jobs=[];seen=set()
        for value in data['jobs']:
            if not isinstance(value,dict) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',str(value.get('key',''))):
                raise ValueError('Each key must be unique ASCII letters/digits/_/-, 1 to 64 characters')
            key=value['key']
            if key.upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
                raise ValueError('Reserved filesystem job key: '+key)
            if key.lower() in seen: raise ValueError('Duplicate job key: '+key)
            seen.add(key.lower())
            if not isinstance(value.get('product'),str) or not value['product'].strip():
                raise ValueError('Each job needs a nonempty product label')
            focus=value.get('focus',[])
            if isinstance(focus,str):focus=[focus]
            if not isinstance(focus,list) or any(not isinstance(f,str) for f in focus):
                raise ValueError('focus must be a string or string array')
            if sum(len(focus_range(f)['times']) for f in focus)>2000:
                raise ValueError('At most 2000 focus samples per job')
            job={'key':key,'product':value['product'],'focus':focus,'inputs':{}}
            for field in ('video','original_audio','source_video'):
                if field=='source_video' and not value.get(field):continue
                path=Path(value[field]).expanduser().resolve(strict=True)
                job[field]=str(path);job['inputs'][field]=signature(path)
            jobs.append(job)
        identity={'schema':SCHEMA,'jobs':jobs,'scripts':{p.name:sha256(p) for p in (Path(__file__).resolve(),REVIEW)},
                  'ffmpeg':{'path':ffmpeg,'version':tool_version},
                  'ffprobe':{'path':ffprobe,'version':probe_version} if ffprobe else None}
        output=Path(args.out).expanduser().resolve()
        if output.exists() and not args.reuse:
            raise ValueError('Output exists; choose a new folder or use --reuse for identical inputs/tools')
        if not output.exists():
            if args.reuse:raise ValueError('--reuse needs an existing signed output folder')
            output.mkdir(parents=True,exist_ok=False)
        with output_lock(output):
            session=output/'session.json'
            if session.exists():
                if read_json(session).get('identity')!=identity:
                    raise ValueError('Input, options or tool signature changed; choose a new output folder; existing files untouched')
            else:
                if args.reuse:raise ValueError('Unsigned folder; cannot safely reuse')
                atomic_json(session,{'identity':identity,'created_utc':utc(),
                                    'manifest':str(manifest),'scope':'Local-only preparation; no task-record write or acceptance'})
            results=[]
            with ThreadPoolExecutor(max_workers=args.jobs) as executor:
                pending={executor.submit(prepare_job,j,output,ffmpeg,ffprobe):j['key'] for j in jobs}
                for future in as_completed(pending):
                    try:
                        result=future.result()
                    except Exception as exc:
                        result={'key':pending[future],'status':'failed','error':str(exc),'final_verdict':'未审核'}
                    results.append(result)
                    print(json.dumps(result,ensure_ascii=True),flush=True)
                    atomic_json(output/'results.json',{'updated_utc':utc(),'jobs':sorted(results,key=lambda r:r['key']),
                                'all_jobs_reported':len(results)==len(jobs),'final_verdict':'未审核'})
            report={'updated_utc':utc(),'jobs':sorted(results,key=lambda r:r['key']),
                    'all_jobs_reported':True,'wall_clock_seconds':round(time.perf_counter()-started,4),
                    'local_workers':args.jobs,'final_verdict':'未审核'}
            atomic_json(output/'results.json',report)
            print(json.dumps({'output':str(output),'prepared':sum(r['status']=='prepared' for r in results),
                              'failed':sum(r['status']=='failed' for r in results),'wall_clock_seconds':report['wall_clock_seconds']},ensure_ascii=True))
            return 0 if all(r['status']=='prepared' for r in results) else 2
    except (OSError,ValueError,RuntimeError,KeyError,TypeError,argparse.ArgumentTypeError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=True),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
