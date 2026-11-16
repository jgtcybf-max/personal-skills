"""Local collection helpers; no network, messages or source mutations."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import base64
import json
import os
import re
import subprocess

TZ = timezone(timedelta(hours=8))
SKILL = Path(__file__).resolve().parent.parent


def load_config(path=None):
    return json.loads(Path(path or SKILL / 'config.json').read_text(encoding='utf-8'))


def date_window(date=None, start=None, end=None, days=7, now=None):
    now = now or datetime.now(TZ)
    def parse(value):
        if value == 'today': return now.date()
        if value == 'yesterday': return now.date() - timedelta(days=1)
        return datetime.strptime(value, '%Y-%m-%d').date()
    if date:
        if start or end: raise ValueError('--date cannot be combined with --start/--end')
        first = last = parse(date)
    else:
        last = parse(end) if end else now.date()
        first = parse(start) if start else last - timedelta(days=days-1)
    if first > last: raise ValueError('Start must not follow end')
    begin = datetime.combine(first, datetime.min.time(), TZ)
    finish = min(datetime.combine(last+timedelta(days=1), datetime.min.time(), TZ), now)
    if begin >= finish: raise ValueError('Requested window is entirely in the future')
    return begin, finish


def add_window_args(parser):
    parser.add_argument('--date', help='today, yesterday or YYYY-MM-DD')
    parser.add_argument('--start', help='Inclusive Beijing date YYYY-MM-DD')
    parser.add_argument('--end', help='Inclusive Beijing date YYYY-MM-DD')
    parser.add_argument('--days', type=int, default=7)


def protect_directory(path):
    """Fail closed before writing private excerpts on Windows."""
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt':
        path.chmod(0o700)
        return
    literal = str(path).replace("'", "''")
    code = (
        "$ErrorActionPreference='Stop';"
        "$acl=[System.Security.AccessControl.DirectorySecurity]::new();"
        "$acl.SetAccessRuleProtection($true,$false);"
        "$owner=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name;"
        "foreach($p in @($owner,'NT AUTHORITY\\SYSTEM')){"
        "$rule=[System.Security.AccessControl.FileSystemAccessRule]::new"
        "($p,'FullControl','ContainerInherit,ObjectInherit','None','Allow');"
        "$acl.AddAccessRule($rule)};"
        f"[System.IO.Directory]::SetAccessControl('{literal}',$acl)"
    )
    encoded = base64.b64encode(code.encode('utf-16-le')).decode('ascii')
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode: raise RuntimeError('Unable to restrict private output permissions')


def redact(text):
    """Redact before truncation and before writing any excerpt."""
    text = str(text or '')
    text = re.sub(r'(?s)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----', '[私钥省略]', text)
    text = re.sub(r'\bsk-[\w-]{12,}', '[密钥省略]', text)
    text = re.sub(r'\beyJ[\w-]{10,}(?:\.[\w-]+){1,4}', '[令牌省略]', text)
    text = re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]{8,}', r'\1[省略]', text)
    text = re.sub(r'(?im)^.*(?:验证码|访问码|设备码|设备代码|安全码|开户行|银行卡|银行账号|税号|统一社会信用代码|收款账户|UU远程|ToDesk|AnyDesk).*$', '[账号、财务或远程信息省略]', text)
    text = re.sub(r'(?im)^.*(?:api[_ .-]?key|access[_ .-]?token|refresh[_ .-]?token|session[_ .-]?token|client[_ .-]?secret|authorization|password|密码|密钥|口令)\s*[=:：].*$', '[配置凭据省略]', text)
    text = re.sub(r'(?i)([?&](?:key|token|signature|sign|auth|aeskey|secret|password|filekey|authkey|sharecode)=)[^&\s<>]+', r'\1[省略]', text)
    text = re.sub(r'(?i)\b(?:aeskey|cdn\w*(?:url|key)|fileuploadtoken|attachid)\s*=\s*["\'][^"\']*["\']', '[媒体凭据省略]', text)
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[邮箱省略]', text)
    text = re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)', '[手机号省略]', text)
    text = re.sub(r'(?i)\b(?:https?://)?(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?(?:/[^\s<>]*)?', '[IP省略]', text)
    text = re.sub(r'(?<!\d)\d{16,}(?!\d)', '[长编号省略]', text)
    if re.fullmatch(r'\s*\d{4,15}\s*',text): return '[独立数字代码省略]'
    if re.fullmatch(r'[A-Za-z0-9!@#$%^&*_=+-]{12,128}',text.strip()) and re.search(r'[A-Za-z]',text) and re.search(r'\d',text):
        return '[独立代码或疑似凭据省略]'
    return text


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')


def write_jsonl(path, records):
    with Path(path).open('w',encoding='utf-8') as stream:
        for record in records: stream.write(json.dumps(record,ensure_ascii=False)+'\n')
