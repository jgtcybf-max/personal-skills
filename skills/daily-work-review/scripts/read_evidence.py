"""Page through a collected source, preserving source references and line IDs."""
import argparse
import json
from pathlib import Path
import sys

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run',required=True,type=Path)
parser.add_argument('--source',choices=['wechat','codex'],required=True)
parser.add_argument('--day',help='YYYY-MM-DD')
parser.add_argument('--chat',help='WeChat name or username substring')
parser.add_argument('--thread',help='Codex thread UUID')
parser.add_argument('--self-only',action='store_true')
parser.add_argument('--offset',type=int,default=0)
parser.add_argument('--limit',type=int,default=120)
args=parser.parse_args()
if args.offset<0 or args.limit<1: parser.error('offset must be nonnegative and limit positive')
name='wechat.jsonl' if args.source=='wechat' else 'codex_events.jsonl'
path=args.run/'private'/name
sys.stdout.reconfigure(encoding='utf-8')
total=shown=0
with path.open(encoding='utf-8') as stream:
    for line_no,line in enumerate(stream,1):
        row=json.loads(line)
        if args.day and row.get('date',row.get('time','')[:10])!=args.day: continue
        if args.chat and args.chat not in row.get('chat_name','') and args.chat not in row.get('chat',''): continue
        if args.thread and row.get('thread_id')!=args.thread: continue
        if args.self_only and not row.get('is_self'): continue
        if args.offset<=total<args.offset+args.limit:
            row['excerpt_source']={'path':str(path.resolve()),'line':line_no}
            print(json.dumps(row,ensure_ascii=False)); shown+=1
        total+=1
print(json.dumps({'matched':total,'shown':shown,'offset':args.offset,'next_offset':args.offset+shown if total>args.offset+shown else None},ensure_ascii=False))
