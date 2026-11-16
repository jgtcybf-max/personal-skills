/* Isolated local UI tests. Never connects to Superdirector or creates paid jobs. */
'use strict';
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { createHash } = require('node:crypto');
const { deflateSync } = require('node:zlib');
const helper = require('./batch.cjs');
let browser, server, base, root, activeDownloads = 0, peakDownloads = 0;

function png(color) {
  const chunk = (type, bytes) => {
    const data = Buffer.concat([Buffer.from(type), bytes]);
    let crc = -1;
    for (const b of data) { crc ^= b; for (let i = 0; i < 8; i++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1)); }
    const size = Buffer.alloc(4), sum = Buffer.alloc(4);
    size.writeUInt32BE(bytes.length); sum.writeUInt32BE((crc ^ -1) >>> 0);
    return Buffer.concat([size, data, sum]);
  };
  const header = Buffer.alloc(13); header.writeUInt32BE(1, 0); header.writeUInt32BE(1, 4); header[8] = 8; header[9] = 2;
  return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]), chunk('IHDR', header),
    chunk('IDAT', deflateSync(Buffer.from([0, color % 256, 90, 150]))), chunk('IEND', Buffer.alloc(0))]);
}

const html = `<!doctype html><meta charset="utf-8"><div id="history"></div>
<div id="composer"><div id="settings"><div>GPT Image2.5 精绘版</div><div>9:16</div><div>2K</div><div>1张</div></div>
<div contenteditable="true"></div><div id="stack"></div><input type="file" multiple>
<button class="_send_btn_mock">发送</button></div><script>
window.fixture = {uploadDelay:0, failUpload:false, templateDelay:0, sendMode:'normal', sendDelay:0, sends:[], uploads:0};
let nonce = 0;
function item(url) {
  const e = document.createElement('div'); e.className='_stack_item_mock';
  e.innerHTML='<img width="8" height="8"><input type="file"><button class="_delete_btn_mock">删除</button>';
  if (url) e.querySelector('img').src=url;
  e.querySelector('button').onclick=()=>e.remove();
  e.querySelector('input').onchange=ev=>upload(e, ev.target.files[0]);
  document.querySelector('#stack').append(e); return e;
}
function upload(e, file) {
  fixture.uploads++;
  const seq=++nonce;
  setTimeout(()=>{
    if (!e.isConnected) return;
    if (fixture.failUpload) { const err=document.createElement('span'); err.className='_error_mock'; err.textContent='上传失败'; e.append(err); return; }
    e.querySelector('img').src='/image/'+encodeURIComponent(file.name)+'?v='+seq;
  },fixture.uploadDelay);
}
document.querySelector('input[multiple]').onchange=ev=>{
  document.querySelector('#stack').replaceChildren();
  for (const file of ev.target.files) upload(item(), file);
};
document.querySelector('._send_btn_mock').onclick=()=>{
  const prompt=document.querySelector('[contenteditable]').innerText;
  const urls=[...document.querySelectorAll('#stack img')].map(e=>e.src);
  fixture.sends.push({prompt,urls});
  if (fixture.sendMode==='ignore') return;
  setTimeout(()=>{
    const g=document.createElement('div'); g.className='_message_group_mock'; g.id='message-'+fixture.sends.length;
    const p=document.createElement('p'); p.textContent=prompt; g.append(p);
    const b=document.createElement('button'); b.textContent='使用参考图'; b.onclick=()=>{
      document.querySelector('#stack').replaceChildren();
      setTimeout(()=>urls.forEach(url=>item(url)),fixture.templateDelay);
    }; g.append(b);
    const r=document.createElement('div'); r.className='_response_area_mock'; r.textContent='正在生成'; g.append(r);
    document.querySelector('#history').append(g);
    document.querySelector('#stack').replaceChildren(); document.querySelector('[contenteditable]').textContent='';
  },fixture.sendDelay);
};
window.complete=(number,url)=>{
  const r=document.querySelectorAll('._response_area_mock')[number-1]; r.replaceChildren();
  const im=document.createElement('img'); im.src=url||('/result/'+number+'.png'); im.width=8; im.height=8; r.append(im);
};
<\/script>`;

before(async () => {
  root = await fs.mkdtemp(path.join(os.tmpdir(), 'superdirector-skill-test-'));
  server = http.createServer((req, res) => {
    if (req.url.startsWith('/bad-result')) { res.writeHead(200, {'Content-Type':'image/gif'}); res.end('GIF89a'); return; }
    if (req.url.startsWith('/image/') || req.url.startsWith('/result/')) {
      const result = req.url.startsWith('/result/');
      const bytes = png(Number(req.url.match(/\d+/)?.[0] || 1));
      if (result) { activeDownloads++; peakDownloads = Math.max(peakDownloads, activeDownloads); }
      setTimeout(() => {
        res.writeHead(200, {'Content-Type':'image/png'}); res.end(bytes);
        if (result) activeDownloads--;
      }, result ? 60 : 0);
      return;
    }
    res.writeHead(200, {'Content-Type':'text/html; charset=utf-8'}); res.end(html);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  base = 'http://127.0.0.1:' + server.address().port;
  let pw;
  try { pw = require('playwright'); } catch { pw = require(path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')); }
  const candidates = [process.env.SUPERDIRECTOR_TEST_BROWSER, pw.chromium.executablePath(),
    'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].filter(Boolean);
  let executablePath;
  for (const candidate of candidates) { try { await fs.access(candidate); executablePath=candidate; break; } catch {} }
  if (!executablePath) throw new Error('No local test browser. Set SUPERDIRECTOR_TEST_BROWSER to an installed Chromium executable.');
  browser = await pw.chromium.launch({headless:true, executablePath});
});
after(async () => { await browser?.close(); await new Promise(resolve => server?.close(resolve)); });

async function setup(t, count = 3, custom = {}) {
  const dir = await fs.mkdtemp(path.join(root, 'case-'));
  const source = path.join(dir, 'frames'), refs = path.join(dir, 'refs'), output = path.join(dir, 'output');
  await Promise.all([fs.mkdir(source), fs.mkdir(refs)]);
  const manifest = { schemaVersion:1, runId:path.basename(dir), output, refs:[], frames:[] };
  for (let n=1;n<=2;n++) { const p=path.join(refs, 'ref'+n+'.png'); await fs.writeFile(p,png(n)); manifest.refs.push(p); }
  for (let n=1;n<=count;n++) { const p=path.join(source,n+'.png'); await fs.writeFile(p,png(n)); manifest.frames.push({index:n,source:p,outputName:n+'.png',messageId:null,saved:null}); }
  Object.assign(manifest, custom);
  const manifestPath=path.join(dir,'batch.json'); await fs.writeFile(manifestPath,JSON.stringify(manifest));
  const page=await browser.newPage(); await page.goto(base+'/micro_aigc/?session_id='+path.basename(dir));
  const options={manifestPath,prompt:'只替换图片1的鞋，图片2、3是同款商品参考。',expectedSettings:['GPT Image2.5 精绘版','9:16','2K','1张'],
    timing:{uploadWaitMs:150,templateWaitMs:150,stallMs:500,pollMs:20,sendMs:150,downloadMs:2000}};
  const run=await helper.openBatch(page,options);
  t.after(async()=>{try {run.detach();}catch {} await page.close();});
  return {dir,page,run,options,output,manifestPath,read:async()=>JSON.parse(await fs.readFile(manifestPath,'utf8'))};
}
async function approved(c) {
  assert.equal((await c.run.stage(1)).status,'staged'); await c.run.submit(1);
  await c.page.evaluate(()=>complete(1)); await c.run.collect(); await c.run.approveFirstFrame(1);
}

test('first-frame gate, reusable references, continuous submissions before results, parallel downloads',async t=>{
  const c=await setup(t,5);
  assert.equal((await c.run.pump()).status,'first-frame-review');
  assert.equal((await c.run.status()).submitted,1);
  await c.page.evaluate(()=>complete(1)); await c.run.collect(); await c.run.approveFirstFrame(1);
  assert.equal((await c.run.pump({maxSubmissions:10,budgetMs:10000})).status,'all-submitted');
  const sends=await c.page.evaluate(()=>fixture.sends);
  assert.equal(sends.length,5); assert.equal(await c.page.locator('._response_area_mock').filter({hasText:'正在生成'}).count(),4);
  for(let n=0;n<5;n++) {
    assert.match(sends[n].urls[0],new RegExp('/image/'+(n+1)+'\\.png'));
    assert.deepEqual(sends[n].urls.slice(1),sends[0].urls.slice(1));
  }
  assert.equal(await c.page.evaluate(()=>fixture.uploads),7); // 3 initial images, then only one frame per task.
  await c.page.evaluate(()=>{for(let n=2;n<=5;n++)complete(n);});
  peakDownloads=0;
  assert.equal((await c.run.collect({downloadConcurrency:3})).saved,5);
  assert.ok(peakDownloads>=2,'results fetched concurrently');
  const m=await c.read(); assert.deepEqual(m.frames.map(f=>path.basename(f.saved)),['1.png','2.png','3.png','4.png','5.png']);
  assert.equal(new Set(m.frames.map(f=>f.expectedSha256)).size,5);
});

test('delayed background upload resumes without sending the previous scene',async t=>{
  const c=await setup(t); await approved(c);
  await c.page.evaluate(()=>{fixture.uploadDelay=180; window.requestAnimationFrame=()=>0;});
  assert.equal((await c.run.stage(2,{waitMs:30})).status,'uploading');
  await assert.rejects(c.run.submit(2),/Stage first/);
  assert.equal((await c.run.stage(2,{waitMs:400})).status,'staged'); await c.run.submit(2);
  const sends=await c.page.evaluate(()=>fixture.sends); assert.equal(sends.length,2); assert.match(sends[1].urls[0],/\/image\/2\.png/);
});

test('one failed upload retry then bounded restart recovery',async t=>{
  const c=await setup(t); await c.page.evaluate(()=>fixture.failUpload=true);
  assert.equal((await c.run.stage(1)).status,'upload-failed');
  assert.equal((await c.run.retryUpload(1)).status,'retry-ready');
  assert.equal((await c.run.stage(1)).status,'restart-required');
  assert.equal((await c.run.retryUpload(1)).status,'restart-required');
  assert.equal((await c.read()).frames[0].uploadRetries,1);
  assert.equal(await c.page.evaluate(()=>fixture.sends.length),0);
  await c.page.reload(); await c.run.resumeAfterRestart();
  assert.equal((await c.run.stage(1)).status,'staged');
});

test('stalled upload returns recovery instead of waiting indefinitely',async t=>{
  const c=await setup(t); await c.page.evaluate(()=>fixture.uploadDelay=10000);
  const start=Date.now(); const result=await c.run.pump({budgetMs:2500});
  assert.equal(result.status,'restart-required'); assert.ok(Date.now()-start<2400);
  assert.equal((await c.read()).frames[0].uploadRetries,1);
});

test('uncertain send blocks resend, late message reconciles once',async t=>{
  const c=await setup(t); await c.page.evaluate(()=>fixture.sendDelay=400);
  await c.run.stage(1); await assert.rejects(c.run.submit(1),/Send uncertain/);
  await assert.rejects(c.run.stage(1),/Uncertain send/);
  await c.page.waitForFunction(()=>document.querySelector('._message_group_mock'));
  assert.equal((await c.run.reconcile(1)).found,true);
  assert.equal((await c.run.submit(1)).alreadySubmitted,true);
  assert.equal(await c.page.evaluate(()=>fixture.sends.length),1);
  assert.equal((await c.run.stage(1)).alreadySubmitted,true);
  assert.equal((await c.run.status()).composerIndex,null);
});

test('same handle reused and concurrent or stale writers rejected',async t=>{
  const c=await setup(t); assert.equal(await helper.openBatch(c.page,c.options),c.run);
  const other=await browser.newPage(); t.after(()=>other.close()); await other.goto(c.page.url());
  await assert.rejects(helper.openBatch(other,c.options),/another live page/);
  await c.page.evaluate(()=>fixture.uploadDelay=150);
  const pending=c.run.stage(1); await assert.rejects(c.run.collect(),/await the current/); await pending;
  const m=await c.read(); m.revision++; await fs.writeFile(c.manifestPath,JSON.stringify(m));
  await assert.rejects(c.run.stage(1),/Manifest changed externally/);
});

test('unknown drafts, reference tampering, wrong settings and conversation are preserved or blocked',async t=>{
  const c=await setup(t);
  await c.page.locator('[contenteditable]').fill('用户未提交的内容');
  await assert.rejects(c.run.stage(1),/Unknown draft/);
  assert.equal(await c.page.locator('[contenteditable]').innerText(),'用户未提交的内容');
  await c.page.locator('[contenteditable]').fill(''); await c.run.stage(1);
  await c.page.locator('#settings').evaluate(e=>e.innerHTML='<div>Wan</div><div>16:9</div>');
  await c.page.locator('#history').evaluate(e=>e.textContent='GPT Image2.5 精绘版\n9:16\n2K\n1张');
  await assert.rejects(c.run.submit(1),/Restore composer settings/);
  await c.page.locator('#history').evaluate(e=>e.textContent='');
  await c.page.locator('#settings').evaluate(e=>e.innerHTML='<div>GPT Image2.5 精绘版</div><div>9:16</div><div>2K</div><div>1张</div>');
  await c.run.submit(1); await c.page.evaluate(()=>complete(1)); await c.run.collect(); await c.run.approveFirstFrame(1);
  await c.run.stage(2);
  await c.page.locator('#stack img').nth(1).evaluate(im=>im.src='/image/changed.png');
  await assert.rejects(c.run.submit(2),/Composer differs/);
  await c.page.evaluate(()=>history.replaceState({},'', '?session_id=other'));
  await assert.rejects(c.run.collect(),/Wrong conversation/);
});

test('restart preserves submitted IDs and saved files, missing history never resets paid jobs',async t=>{
  const c=await setup(t); await approved(c); await c.run.stage(2); await c.run.submit(2);
  const saved=(await c.read()).frames[0].saved;
  await c.run.resumeAfterRestart();
  const m=await c.read(); assert.equal(m.frames[1].messageId,'message-2'); assert.equal(m.frames[0].saved,saved);
  assert.equal(m.frames[2].submissionState,'planned');
  await c.page.locator('#history').evaluate(e=>e.replaceChildren());
  await assert.rejects(c.run.resumeAfterRestart(),/Uncertain\/missing/);
  assert.equal((await c.read()).frames[1].messageId,'message-2');
});

test('downloads reject disguised GIFs and never overwrite unknown files',async t=>{
  const c=await setup(t); await c.run.stage(1); await c.run.submit(1);
  await c.page.evaluate(()=>complete(1,'/bad-result.png'));
  assert.match((await c.run.collect()).updates[0].reason,/not a PNG/);
  await c.page.evaluate(()=>complete(1));
  await fs.mkdir(c.output); const target=path.join(c.output,'1.png'); await fs.writeFile(target,'existing');
  assert.match((await c.run.collect()).updates[0].reason,/conflicts/);
  assert.equal(await fs.readFile(target,'utf8'),'existing');
});

test('checkpointed output from interrupted collection is recovered without regeneration',async t=>{
  const c=await setup(t); await c.run.stage(1); await c.run.submit(1); await c.page.evaluate(()=>complete(1));
  c.run.detach(); const m=await c.read(); const bytes=png(1);
  m.frames[0].expectedSha256=createHash('sha256').update(bytes).digest('hex');
  await fs.writeFile(c.manifestPath,JSON.stringify(m)); await fs.mkdir(c.output); await fs.writeFile(path.join(c.output,'1.png'),bytes);
  const recovered=await helper.openBatch(c.page,c.options); t.after(()=>recovered.detach());
  assert.equal((await recovered.collect()).saved,1);
  assert.equal(await c.page.evaluate(()=>fixture.sends.length),1);
});
