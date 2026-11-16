"""Collect fresh evidence for the callable daily-work-review assistant."""
from pathlib import Path
from datetime import datetime
import argparse
import json
import sys
import uuid

from common import TZ, add_window_args, date_window, load_config, protect_directory, redact, write_json, write_jsonl
from codex_activity import collect as collect_codex


def cached_wechat(path,start,end):
    messages=[]
    with Path(path).open(encoding='utf-8') as stream:
        for n,line in enumerate(stream,1):
            row=json.loads(line)
            stamp=datetime.fromisoformat(row['time'])
            if not stamp.tzinfo or not start<=stamp<end: continue
            row['text']=redact(row.get('text',row.get('body','')))
            row.pop('body',None)
            row['date']=stamp.astimezone(TZ).date().isoformat()
            row['cached_source']={'path':str(Path(path).resolve()),'line':n}
            row.setdefault('id','cached-w-'+str(n))
            messages.append(row)
    return {'status':'cached','messages':messages,'issues':['使用显式指定的历史摘录，不代表已读取最新微信。'],
            'coverage':{'messages':len(messages),'first':messages[0]['time'] if messages else None,
                        'last':messages[-1]['time'] if messages else None,'source_writes':False,
                        'self_voice_untranscribed':sum(m.get('is_self',False) and m.get('type')==34 for m in messages)}}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    add_window_args(parser)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--wechat-cache',type=Path,help='Explicit dated fallback only; marks coverage as cached')
    parser.add_argument('--skip-wechat',action='store_true')
    args=parser.parse_args(argv)
    config=load_config(args.config)
    if args.days<1: parser.error('--days must be positive')
    start,end=date_window(args.date,args.start,args.end,args.days)
    now=datetime.now(TZ)
    run=args.output or Path(config['output_root'])/(now.strftime('%Y-%m-%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    run=run.resolve()
    if run.exists() and any(run.iterdir()): raise RuntimeError('Output directory must be new or empty')
    run.mkdir(parents=True,exist_ok=True); private=run/'private'; protect_directory(private)
    if args.skip_wechat:
        wechat={'status':'skipped','messages':[],'coverage':{},'issues':['此次明确跳过微信，不能据此概括完整一天。']}
    elif args.wechat_cache:
        wechat=cached_wechat(args.wechat_cache,start,end)
    else:
        try:
            from wechat_activity import collect as collect_wechat
            wechat=collect_wechat(config,start,end,redact)
        except Exception as exc:
            wechat={'status':'unavailable','messages':[],'coverage':{},'issues':[redact(str(exc))]}
    codex=collect_codex(Path(config['codex_home']),start,end,redact)
    write_jsonl(private/'wechat.jsonl',wechat['messages'])
    write_jsonl(private/'codex_events.jsonl',codex['events'])
    write_json(private/'codex_threads.json',codex['threads'])
    coverage={'collected_at':now.isoformat(),'window':{'start':start.isoformat(),'end':end.isoformat(),'timezone':'Asia/Shanghai'},
              'status':'collected' if wechat['status']=='ok' and codex['status']=='ok' else 'partial',
              'wechat':{k:v for k,v in wechat.items() if k!='messages'},
              'codex':{k:v for k,v in codex.items() if k not in ('events','threads')},
              'semantic_report_generated':False,'source_writes':False,'run_directory':str(run)}
    write_json(run/'coverage.json',coverage)
    print(json.dumps({'status':coverage['status'],'run_directory':str(run),'coverage':str(run/'coverage.json'),
                      'wechat_status':wechat['status'],'wechat_records':len(wechat['messages']),
                      'codex_status':codex['status'],'codex_events':len(codex['events']),
                      'next':'Agent reads evidence and writes 简报.md; collection alone is not a finished review.'},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
