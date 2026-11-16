"""Authenticated, WAL-aware, in-memory read of the authorized Weixin account."""
from pathlib import Path
import ctypes
from ctypes import wintypes as wt
from datetime import datetime
from collections import Counter, defaultdict
import hashlib
import hmac
import json
import sqlite3
import struct
import sys
import time
from xml.etree import ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parent/'_deps'))
import zstandard
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from wx_keys import load_keys

PAGE=4096
ZDC=zstandard.ZstdDecompressor()


def main_pid():
    class Entry(ctypes.Structure):
        _fields_=[('size',wt.DWORD),('usage',wt.DWORD),('pid',wt.DWORD),
                  ('heap',ctypes.c_size_t),('module',wt.DWORD),('threads',wt.DWORD),
                  ('parent',wt.DWORD),('priority',wt.LONG),('flags',wt.DWORD),('exe',wt.WCHAR*260)]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=[wt.DWORD,wt.DWORD]
    kernel.CreateToolhelp32Snapshot.restype=wt.HANDLE
    kernel.Process32FirstW.argtypes=[wt.HANDLE,ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes=[wt.HANDLE,ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes=[wt.HANDLE]
    handle=kernel.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    processes=[]
    try:
        entry=Entry(); entry.size=ctypes.sizeof(Entry)
        more=kernel.Process32FirstW(handle,ctypes.byref(entry))
        while more:
            if entry.exe.lower() in ('weixin.exe','weixin'): processes.append((entry.pid,entry.parent))
            more=kernel.Process32NextW(handle,ctypes.byref(entry))
    finally: kernel.CloseHandle(handle)
    ids={p for p,_ in processes}
    roots=[p for p,parent in processes if parent not in ids]
    if len(roots)!=1: raise RuntimeError('微信未运行或主进程不唯一，请登录对应微信；不要重启或扫描其他程序。')
    return roots[0]


def checksum(data,a,b,endian):
    words=struct.unpack(endian+str(len(data)//4)+'I',data)
    for i in range(0,len(words),2):
        a=(a+words[i]+b)&0xffffffff
        b=(b+words[i+1]+a)&0xffffffff
    return a,b


def wal_pages(data):
    if not data or len(data)<32: return {},None
    magic,version,page_size,seq,salt1,salt2,c1,c2=struct.unpack('>8I',data[:32])
    if magic not in (0x377f0682,0x377f0683) or page_size!=PAGE: raise RuntimeError('Unsupported WAL header')
    endian='<' if magic==0x377f0682 else '>'
    a,b=checksum(data[:24],0,0,endian)
    if (a,b)!=(c1,c2): raise RuntimeError('WAL header checksum failed')
    frames=[]; committed=0; db_size=None
    for offset in range(32,len(data)-PAGE-23,PAGE+24):
        head=data[offset:offset+24]
        pgno,size,s1,s2,x,y=struct.unpack('>6I',head)
        if (s1,s2)!=(salt1,salt2): break
        payload=data[offset+24:offset+24+PAGE]
        aa,bb=checksum(head[:8]+payload,a,b,endian)
        if (aa,bb)!=(x,y): break
        a,b=aa,bb; frames.append((pgno,payload))
        if size: committed=len(frames); db_size=size
    return dict(frames[:committed]),db_size


def state(path):
    try:
        stat=path.stat(); return stat.st_size,stat.st_mtime_ns
    except FileNotFoundError: return None


def memory_connect(db,rel,meta,checks):
    src=db/rel; wal=Path(str(src)+'-wal')
    for attempt in range(8):
        before=[state(p) for p in (src,wal)]
        try: raw=src.read_bytes(); wal_raw=wal.read_bytes() if wal.exists() else None
        except FileNotFoundError: continue
        if before==[state(p) for p in (src,wal)]: break
        time.sleep(.2)
    else: raise RuntimeError('微信数据库持续变化，未取得稳定只读快照：'+rel)
    if len(raw)%PAGE: raise RuntimeError('Unaligned database')
    overrides,size=wal_pages(wal_raw); total=size or len(raw)//PAGE
    key=bytes.fromhex(meta['enc_key'])
    mac_key=hashlib.pbkdf2_hmac('sha512',key,bytes(v^0x3a for v in raw[:16]),2,32)
    plain=bytearray(total*PAGE)
    for pgno in range(1,total+1):
        page=overrides.get(pgno,raw[(pgno-1)*PAGE:pgno*PAGE])
        if len(page)!=PAGE: raise RuntimeError('Missing database page')
        if page==bytes(PAGE): continue
        start=16 if pgno==1 else 0
        expected=hmac.new(mac_key,page[start:4032]+struct.pack('<I',pgno),hashlib.sha512).digest()
        if not hmac.compare_digest(expected,page[4032:]): raise RuntimeError('微信页认证失败，停止读取。')
        decryptor=Cipher(algorithms.AES(key),modes.CBC(page[4016:4032])).decryptor()
        value=(b'SQLite format 3\0' if pgno==1 else b'')+decryptor.update(page[start:4016])+decryptor.finalize()+bytes(80)
        plain[(pgno-1)*PAGE:pgno*PAGE]=value
    # Committed WAL is already applied; normalize only the isolated memory image.
    plain[18:20]=b'\x01\x01'
    con=sqlite3.connect(':memory:'); con.deserialize(plain); con.execute('PRAGMA query_only=ON')
    if 'fts' not in rel and con.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:
        con.close(); raise RuntimeError('微信内存快照完整性检查未通过。')
    checks.append({'database':rel,'authenticated_pages':total,'committed_wal_pages':len(overrides),'stable_source':True})
    return con


def decode(value,ct=None):
    if value is None: return ''
    if isinstance(value,bytes):
        if ct==4 or value.startswith(b'\x28\xb5\x2f\xfd'):
            value=ZDC.decompress(value,max_output_size=8*1024*1024)
        return value.decode('utf-8',errors='replace')
    return str(value)


def render(text,kind,sender):
    if text.startswith(sender+':\n'): text=text[len(sender)+2:]
    if kind==1: return text
    if kind in (3,34,43,47,62):
        return {3:'[图片，未视觉分析]',34:'[语音，未转写]',43:'[视频，未逐项验收]',47:'[表情]',62:'[小视频]'}[kind]
    if text.lstrip().startswith('<'):
        try:
            root=ET.fromstring(text); app=root.find('.//appmsg')
            if app is not None:
                title=app.findtext('title',''); desc=app.findtext('des','')
                parts=['[分享/附件/引用]',title]
                if desc and desc!=title: parts.append(desc)
                quote=app.find('.//refermsg')
                if quote is not None:
                    content=quote.findtext('content','')
                    if '<' in content and '>' in content: content='[引用的结构化消息省略]'
                    parts.append('[引用内容，非当前发言] '+content[:1200])
                return '\n'.join(parts)
            return '[系统/结构化消息，未展开]'
        except ET.ParseError: return '[结构化消息，未解析]'
    return text[:20000]


def collect(config,start,end,scrub,pid=None):
    db=Path(config['wechat_root'])/'db_storage'; self_id=config['wechat_self']
    if not db.is_dir(): raise RuntimeError('配置的微信账号目录不存在。')
    selected=pid or main_pid(); keys,scan=load_keys(db,selected); checks=[]; issues=[]; messages=[]
    required=['contact/contact.db']+[str(p.relative_to(db)).replace('\\','/') for p in sorted((db/'message').glob('message_[0-9]*.db'))]
    if not all(rel in keys for rel in required): raise RuntimeError('当前微信版本/进程未获得全部认证数据库，未输出部分猜测。')
    con=memory_connect(db,required[0],keys[required[0]],checks)
    contacts={u:scrub(r or n or a or u) for u,r,n,a in con.execute('select username,remark,nick_name,alias from contact')}; con.close()
    known_hash={}
    for rel in required[1:]:
        con=memory_connect(db,rel,keys[rel],checks)
        names=dict(con.execute('select rowid,user_name from Name2Id'))
        chats={hashlib.md5(u.encode()).hexdigest():u for u in names.values()}
        tables=[n for n, in con.execute("select name from sqlite_master where type='table' and name like 'Msg_%'")]
        for table in tables:
            chat=chats.get(table[4:])
            if not chat: continue
            query=f'SELECT local_id,server_id,local_type,sort_seq,real_sender_id,create_time,message_content,compress_content,WCDB_CT_message_content FROM "{table}" WHERE create_time>=? AND create_time<? ORDER BY create_time,sort_seq'
            for lid,sid,typ,seq,senderid,ts,raw,compressed,ct in con.execute(query,(start.timestamp(),end.timestamp())):
                sender=names.get(senderid,f'unknown_sender_{senderid}'); kind=typ&0xffffffff
                try:
                    text=decode(raw,ct)
                    if not text and compressed: text=decode(compressed,4)
                    raw_body=render(text,kind,sender)
                except Exception:
                    raw_body='[消息解码失败]'; issues.append('消息解码失败：'+rel+':'+str(lid))
                body=scrub(raw_body)
                identity=(chat,str(sid)) if sid else (chat,str(ts),sender,str(kind),hashlib.sha256(raw_body.encode()).hexdigest())
                record_id='w-'+hashlib.sha256('|'.join(identity).encode()).hexdigest()[:18]
                known_hash[record_id]=hashlib.sha256(raw_body.encode()).hexdigest()
                messages.append({'id':record_id,'time':datetime.fromtimestamp(ts,start.tzinfo).isoformat(),'ts':ts,'date':datetime.fromtimestamp(ts,start.tzinfo).date().isoformat(),'chat':chat,'chat_name':contacts.get(chat,chat),'sender':sender,'sender_name':'我' if sender==self_id else contacts.get(sender,sender),'is_self':sender==self_id,'type':kind,'text':body,'sort_seq':seq,'source':{'database':str(db/rel),'table':table,'local_id':lid,'server_id':sid}})
        con.close()
    messages=sorted({m['id']:m for m in messages}.values(),key=lambda m:(m['ts'],m['sort_seq']))
    matched=set(); agree=disagree=0
    fts='message/message_fts.db'
    if fts in keys:
        con=memory_connect(db,fts,keys[fts],checks); names=dict(con.execute('select rowid,username from name2id'))
        lookup=defaultdict(list)
        for m in messages:
            if m['type']==1: lookup[(m['chat'],m['ts'],known_hash[m['id']])].append(m)
        for table, in con.execute("select name from sqlite_master where name like 'message_fts_v4_%_content'"):
            for raw,ts,chatid,senderid in con.execute(f'SELECT c0,c6,c4,c5 FROM "{table}" WHERE c6>=? AND c6<?',(int(start.timestamp()),int(end.timestamp()))):
                if not isinstance(raw,str): continue
                sender=names.get(senderid,''); fingerprint=hashlib.sha256(render(raw,1,sender).encode()).hexdigest()
                for m in lookup.get((names.get(chatid,''),ts,fingerprint),[]):
                    if m['id'] in matched: continue
                    matched.add(m['id'])
                    if m['is_self']==(sender==self_id): agree+=1
                    else: disagree+=1
        con.close()
    else: issues.append('未取得FTS认证映射，发送者未做独立索引复核。')
    keys.clear(); known_hash.clear()
    if disagree:
        issues.append('发现FTS发送者映射不一致；相应记录不确认本人。')
        # A mismatch makes the source unsafe for ownership inference until reviewed.
        for m in messages: m['sender_verification']='requires_review'
    return {'status':'partial' if issues else 'ok','messages':messages,'issues':issues,'coverage':{
        'start':start.isoformat(),'end':end.isoformat(),'first':messages[0]['time'] if messages else None,
        'last':messages[-1]['time'] if messages else None,'messages':len(messages),'self_messages':sum(m['is_self'] for m in messages),
        'self_voice_untranscribed':sum(m['is_self'] and m['type']==34 for m in messages),
        'daily_messages':dict(Counter(m['date'] for m in messages)),
        'sender_crosscheck':{'matched':len(matched),'agree':agree,'disagree':disagree},
        'authenticated_databases':checks,'source_writes':False,'keys_written':False,'plaintext_database_files_written':False}}
