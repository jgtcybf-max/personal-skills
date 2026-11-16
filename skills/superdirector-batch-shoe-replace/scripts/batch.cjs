/* UI-only generation. Bounded upload retries; paid tasks are never blindly resent. */
'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { createHash, randomUUID } = require('node:crypto');
const selectors = {
  group: '[class*="_message_group_"]', stack: '[class*="_stack_item_"]',
  editor: '[contenteditable="true"]', response: '[class*="_response_area_"]',
  send: 'button[class*="_send_btn_"]', remove: '[class*="_delete_btn_"]',
};
const sessions = new Map(), pageOwners = new WeakMap();
const pngSignature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
const sha256 = value => createHash('sha256').update(value).digest('hex');
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const sessionKey = url => String(url).match(/[?&]session_id=([^&#]+)/)?.[1] || null;

function loadPlaywright(override) {
  for (const candidate of override ? [override] : ['playwright',
    path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')]) {
    try { return require(candidate); } catch (error) { if (override) throw error; }
  }
  throw new Error('Playwright unavailable; supply an installed playwrightPath.');
}
async function connect(endpoint = 'http://127.0.0.1:9333', options = {}) {
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(new URL(endpoint).hostname)) throw new Error('Use a loopback endpoint.');
  const browser = await loadPlaywright(options.playwrightPath).chromium.connectOverCDP(endpoint);
  const page = browser.contexts().flatMap(c => c.pages()).find(p => p.url().includes('/micro_aigc/'));
  if (!page) throw new Error('Open AIGC素材生产 in the desktop app, then reconnect.');
  return { browser, page };
}

async function openBatch(page, options) {
  const manifestPath = path.resolve(options.manifestPath);
  const owner = sessions.get(manifestPath);
  if (owner && owner.page === page && !owner.closed) {
    if (options.prompt && options.prompt !== owner.prompt) throw new Error('An active batch already owns this prompt.');
    return owner.api; // Reopening returns the same writer, never a stale manifest snapshot.
  }
  if (owner && !owner.closed && !owner.page.isClosed()) throw new Error('Batch attached to another live page. Detach it first.');
  const pageOwner = pageOwners.get(page);
  if (pageOwner && !pageOwner.closed) throw new Error('Composer owned by another batch.');
  const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
  if (manifest.schemaVersion !== 1 || !manifest.runId || !manifest.frames?.length || !manifest.refs?.length) {
    throw new Error('Create a valid manifest with files.py plan.');
  }
  const output = path.resolve(manifest.output), indices = new Set(), names = new Set();
  for (const f of manifest.frames) {
    if (!Number.isInteger(f.index) || indices.has(f.index) || path.basename(f.outputName) !== f.outputName
      || !/\.png$/i.test(f.outputName) || names.has(f.outputName.toLowerCase())) throw new Error('Invalid/duplicate frame index or PNG name.');
    indices.add(f.index); names.add(f.outputName.toLowerCase());
    if (path.resolve(path.dirname(f.source)).toLowerCase() === output.toLowerCase()) throw new Error('Output overlaps frames.');
  }
  for (const ref of [...manifest.refs, ...(manifest.uploadRefs || [])]) {
    if (path.resolve(path.dirname(ref)).toLowerCase() === output.toLowerCase()) throw new Error('Output overlaps references.');
  }
  const prompt = options.prompt || manifest.prompt;
  if (!prompt?.trim()) throw new Error('Supply a shoe-specific editing prompt.');
  if (manifest.prompt && manifest.prompt !== prompt && manifest.frames.some(f => f.submissionState)) {
    throw new Error('Do not change the prompt during a submitted batch.');
  }
  manifest.prompt = prompt;
  const s = { ...selectors, ...options.selectors };
  const timing = { uploadWaitMs: 8000, templateWaitMs: 5000, stallMs: 30000, pollMs: 200,
    sendMs: 12000, downloadMs: 12000, ...options.timing };
  const expectedSettings = options.expectedSettings || manifest.expectedSettings || [];
  if (!Array.isArray(expectedSettings) || expectedSettings.some(x => typeof x !== 'string' || !x.trim())) throw new Error('expectedSettings must contain visible setting labels.');
  manifest.expectedSettings = expectedSettings;
  let busy = false;
  const lease = { page, prompt, closed: false, api: null };
  const assertOwner = () => {
    if (lease.closed || sessions.get(manifestPath) !== lease) throw new Error('Batch handle detached; use the new handle.');
  };
  const assertConversation = () => {
    if (manifest.sessionId && manifest.sessionId !== sessionKey(page.url())) throw new Error('Wrong conversation; return to the saved batch.');
  };
  const save = async () => {
    assertOwner();
    const disk = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
    if ((disk.revision || 0) !== (manifest.revision || 0)) throw new Error('Manifest changed externally; detach and inspect before resuming.');
    const revision = (manifest.revision || 0) + 1;
    const temp = manifestPath + '.tmp-' + randomUUID();
    try {
      await fs.writeFile(temp, JSON.stringify({ ...manifest, revision }, null, 2), { encoding: 'utf8', flag: 'wx' });
      await fs.rename(temp, manifestPath);
      manifest.revision = revision;
    } finally { await fs.unlink(temp).catch(() => {}); }
  };
  const exclusive = async action => {
    assertOwner(); assertConversation();
    if (busy) throw new Error('One composer: await the current operation first.');
    busy = true;
    try { return await action(); } finally { busy = false; }
  };
  const frameAt = index => {
    const f = manifest.frames.find(f => f.index === index);
    if (!f) throw new Error('Unknown frame: ' + index);
    f.promptedLabel ||= `批次${manifest.runId} 关键帧${String(index).padStart(3, '0')}`;
    return f;
  };
  const groupFor = f => page.locator(s.group).filter({ hasText: f.promptedLabel });
  const editorText = f => f.promptedLabel + '。' + prompt;
  const sourceFor = f => f.uploadSource || f.source;
  const refs = manifest.uploadRefs || manifest.refs;
  const requireFreeTarget = async f => {
    try { await fs.lstat(path.join(output, f.outputName)); }
    catch (error) { if (error.code === 'ENOENT') return; throw error; }
    throw new Error('Output already exists; never regenerate over an unknown file: ' + f.outputName);
  };
  const reconcileFrame = async f => {
    const g = groupFor(f), count = await g.count();
    if (count > 1) throw new Error('Duplicate task labels; inspect before resending: ' + f.promptedLabel);
    if (!count) return { index: f.index, found: false, state: f.submissionState || 'planned' };
    const id = await g.getAttribute('id');
    if (!id || f.messageId && f.messageId !== id) throw new Error('Message ID absent or changed; do not resend.');
    const changed = f.messageId !== id || f.submissionState !== 'submitted';
    Object.assign(f, { messageId: id, submissionState: 'submitted' });
    manifest.sessionId ||= sessionKey(page.url()); manifest.conversationUrl = page.url();
    if (changed) await save();
    return { index: f.index, found: true, messageId: id };
  };
  const readInputs = () => page.locator(s.stack).evaluateAll(items => items.map(e => {
    const im = e.querySelector('img');
    return { url: im?.src || '', ready: !!im && /^https?:\/\//.test(im.src) && im.complete && im.naturalWidth > 0,
      error: !!e.querySelector('[class*="_error_"]') || /\berror\b|上传失败/i.test(e.innerText) };
  }));
  const waitInputs = async (count, oldFirst, waitMs) => {
    // RAF polling can stop in background/minimized Electron; numeric polling must be explicit.
    if (waitMs > 0) {
      try {
        await page.waitForFunction(({ stack, count, old }) => {
          const items = [...document.querySelectorAll(stack)];
          return items.some(e => e.querySelector('[class*="_error_"]') || /\berror\b|上传失败/i.test(e.innerText))
            || items.length === count && items.every(e => {
              const im = e.querySelector('img');
              return im && /^https?:\/\//.test(im.src) && im.complete && im.naturalWidth > 0;
            }) && (!old || items[0].querySelector('img').src !== old);
        }, { stack: s.stack, count, old: oldFirst }, { timeout: waitMs, polling: timing.pollMs });
      } catch (error) { if (error.name !== 'TimeoutError') throw error; }
    }
    const items = await readInputs(); // Read once more after timeout; a completed upload is resumable.
    return { items, failed: items.some(x => x.error), ready: items.length === count
      && items.every(x => x.ready) && (!oldFirst || items[0].url !== oldFirst) };
  };
  const checkSettings = async () => {
    if (!expectedSettings.length) return;
    const text = await page.locator(s.editor).evaluate((editor, { send, editorSelector, stack }) => {
      let e = editor.parentElement;
      while (e && e !== document.body) {
        if (e.querySelector(send)) {
          // Only control text: prompt text and thumbnail captions cannot satisfy settings.
          const walker = document.createTreeWalker(e, NodeFilter.SHOW_TEXT), parts = [];
          while (walker.nextNode()) {
            const node = walker.currentNode, parent = node.parentElement;
            if (parent && !parent.closest(editorSelector + ',' + stack) && parent.getClientRects().length
              && getComputedStyle(parent).visibility !== 'hidden') parts.push(node.textContent);
          }
          return parts.join(' ').split(/\s+/).filter(Boolean).join('\n');
        }
        e = e.parentElement;
      }
      return '';
    }, { send: s.send, editorSelector: s.editor, stack: s.stack });
    const words = text.split('\n');
    const missing = expectedSettings.filter(x => {
      const expected = x.trim().split(/\s+/);
      return !words.some((_, i) => expected.every((word, n) => words[i + n] === word));
    });
    if (missing.length) throw new Error('Restore composer settings before submitting: ' + missing.join(', '));
  };
  const uploadFailure = async (f, reason) => {
    if (!f.uploadFailureRecorded) {
      f.uploadFailureRecorded = true;
      manifest.consecutiveUploadFailures = (manifest.consecutiveUploadFailures || 0) + 1;
    }
    f.uploadError = reason; f.submissionState = 'upload-failed';
    if ((f.uploadRetries || 0) >= 1 || manifest.consecutiveUploadFailures >= 2) {
      manifest.recoveryRequired = { index: f.index, reason,
        action: (manifest.restartCount || 0) >= 2 ? 'needs-attention' : 'restart-required' };
    }
    await save();
    return { index: f.index, status: manifest.recoveryRequired?.action || 'upload-failed', reason };
  };

  async function stageFrame(index, { waitMs = timing.uploadWaitMs } = {}) {
    const f = frameAt(index), found = await reconcileFrame(f);
    if (found.found) {
      if (manifest.composerIndex === index && !await page.locator(s.stack).count()
        && !(await page.locator(s.editor).innerText()).trim()) {
        manifest.composerIndex = null; await save();
      }
      return { ...found, alreadySubmitted: true };
    }
    if (f.messageId) throw new Error('Submitted message not loaded; return to original conversation.');
    if (['submitting', 'uncertain'].includes(f.submissionState)) throw new Error('Uncertain send: reconcile, never blindly resend.');
    if (manifest.recoveryRequired) return { index, status: manifest.recoveryRequired.action, reason: manifest.recoveryRequired.reason };
    await requireFreeTarget(f);
    const count = await page.locator(s.stack).count();
    if (manifest.composerIndex !== index) {
      if (count || (await page.locator(s.editor).innerText()).trim()) throw new Error('Unknown draft in composer; preserve it.');
      const template = manifest.frames.find(x => x.messageId);
      manifest.composerIndex = index;
      Object.assign(f, { uploadStartedAt: new Date().toISOString(), uploadFailureRecorded: false,
        submissionState: template ? 'reference-loading' : 'uploading', oldFirst: template?.inputUrls?.[0] || null });
      await save(); // Own this draft before mutation; a timeout does not require manual manifest surgery.
      if (template) {
        if (!(await reconcileFrame(frameAt(template.index))).found) throw new Error('Template absent; load batch history.');
        await groupFor(template).getByRole('button', { name: '使用参考图', exact: true }).click({ timeout: timing.templateWaitMs });
      } else {
        await page.locator(s.editor).fill(editorText(f));
        await page.locator('input[type="file"][multiple]').setInputFiles([sourceFor(f), ...refs]);
      }
    } else {
      const text = (await page.locator(s.editor).innerText()).trim();
      if (text && text !== editorText(f)) throw new Error('Draft edited outside this batch; preserve it.');
    }
    if (f.submissionState === 'upload-failed') return { index, status: 'upload-failed', reason: f.uploadError };
    if (f.submissionState === 'reference-loading') {
      const current = await waitInputs(refs.length + 1, null, Math.min(waitMs, timing.templateWaitMs));
      if (!current.ready) return uploadFailure(f, 'Cached reference list failed to load.');
      const urls = current.items.map(x => x.url);
      if (manifest.referenceUrls && !same(urls.slice(1), manifest.referenceUrls)) throw new Error('Cached references changed.');
      Object.assign(f, { oldFirst: urls[0], submissionState: 'uploading', uploadStartedAt: new Date().toISOString() });
      await save();
      await page.locator(s.editor).fill(editorText(f));
      await page.locator(s.stack + ' input[type="file"]').first().setInputFiles(sourceFor(f));
    }
    const current = await waitInputs(refs.length + 1, f.oldFirst, waitMs);
    if (current.failed) return uploadFailure(f, 'Image upload returned an error.');
    if (!current.ready) {
      const elapsedMs = Date.now() - Date.parse(f.uploadStartedAt);
      if (elapsedMs >= timing.stallMs) return uploadFailure(f, 'No server image URL within upload deadline.');
      return { index, status: 'uploading', elapsedMs };
    }
    const urls = current.items.map(x => x.url);
    if (manifest.referenceUrls && !same(urls.slice(1), manifest.referenceUrls)) throw new Error('Reference order/content changed.');
    if (f.submissionState === 'staged' && !same(urls, f.inputUrls)) throw new Error('Staged images changed; inspect before sending.');
    manifest.referenceUrls ||= urls.slice(1);
    await page.locator(s.editor).fill(editorText(f));
    Object.assign(f, { inputUrls: urls, submissionState: 'staged', uploadError: null });
    manifest.consecutiveUploadFailures = 0;
    await save();
    return { index, status: 'staged', inputCount: urls.length };
  }

  async function retryUploadFrame(index) {
    const f = frameAt(index), found = await reconcileFrame(f);
    if (found.found) return found;
    if (f.messageId || f.submissionState !== 'upload-failed' || manifest.composerIndex !== index) throw new Error('Only failed owned uploads may be retried.');
    if (manifest.recoveryRequired) return { index, status: manifest.recoveryRequired.action };
    const text = (await page.locator(s.editor).innerText()).trim();
    if (text && text !== editorText(f)) throw new Error('Unknown draft; preserve it.');
    const count = await page.locator(s.stack).count();
    for (let n = count; n > 0; n--) {
      await page.locator(s.stack).last().locator(s.remove).dispatchEvent('click');
      await page.waitForFunction(({ stack, n }) => document.querySelectorAll(stack).length < n,
        { stack: s.stack, n }, { timeout: 2000, polling: timing.pollMs });
    }
    // Re-selecting the same files can suppress the browser change event unless reset first.
    await page.locator('input[type="file"][multiple]').setInputFiles([]);
    await page.locator(s.editor).fill('');
    Object.assign(f, { uploadRetries: (f.uploadRetries || 0) + 1, submissionState: 'planned', uploadFailureRecorded: false });
    manifest.composerIndex = null; await save();
    return { index, status: 'retry-ready' };
  }

  async function submitFrame(index) {
    const f = frameAt(index), found = await reconcileFrame(f);
    if (found.found) return { ...found, alreadySubmitted: true };
    if (f.submissionState !== 'staged' || manifest.composerIndex !== index) throw new Error('Stage first; never resend uncertain tasks.');
    await requireFreeTarget(f);
    const current = await waitInputs(refs.length + 1, f.oldFirst, 0);
    if (!current.ready || !same(current.items.map(x => x.url), f.inputUrls)
      || (await page.locator(s.editor).innerText()) !== editorText(f)) throw new Error('Composer differs from staged frame.');
    await checkSettings();
    Object.assign(f, { submissionState: 'submitting', submittedAt: new Date().toISOString() }); await save();
    try {
      await page.locator(s.send).click({ timeout: 4000 });
      await groupFor(f).waitFor({ state: 'attached', timeout: timing.sendMs });
      const result = await reconcileFrame(f);
      if (!result.found) throw new Error('Matching task not found after send.');
      manifest.composerIndex = null; await save();
      await page.waitForFunction(stack => !document.querySelector(stack), s.stack, { timeout: 5000, polling: timing.pollMs });
      return result;
    } catch (error) {
      const reconciled = await reconcileFrame(f);
      if (reconciled.found) {
        manifest.composerIndex = null; await save();
        return { ...reconciled, inspectComposerBeforeNextFrame: true };
      }
      f.submissionState = 'uncertain'; f.lastError = String(error.message).slice(0, 250); await save();
      throw new Error('Send uncertain. Reconcile in original conversation; do not resend.');
    }
  }

  const summary = () => ({ total: manifest.frames.length, submitted: manifest.frames.filter(f => f.messageId).length,
    saved: manifest.frames.filter(f => f.saved).length, composerIndex: manifest.composerIndex || null,
    recovery: manifest.recoveryRequired?.action || null, output, conversation: manifest.conversation });
  async function collectFrames({ maxDownloads = 6, downloadConcurrency = 3 } = {}) {
    if (!Number.isInteger(maxDownloads) || maxDownloads < 1 || !Number.isInteger(downloadConcurrency)
      || downloadConcurrency < 1 || downloadConcurrency > 6) throw new Error('Use positive download limits and concurrency 1–6.');
    const updates = [], ready = [];
    for (const f of manifest.frames) {
      if (f.saved || !f.messageId) continue;
      frameAt(f.index);
      const g = groupFor(f);
      if (await g.count() !== 1) { updates.push({ index: f.index, status: 'message-not-loaded' }); continue; }
      if (await g.getAttribute('id') !== f.messageId) throw new Error('Message ID changed during collection.');
      const response = g.locator(s.response), text = await response.innerText();
      if (/生成失败|任务失败|失败原因|服务异常/.test(text)) {
        f.generationError = text.slice(-400); updates.push({ index: f.index, status: 'failed', reason: f.generationError }); continue;
      }
      if (/正在生成|排队|等待生成/.test(text)) { updates.push({ index: f.index, status: 'generating' }); continue; }
      if (ready.length >= maxDownloads) continue;
      await response.scrollIntoViewIfNeeded({ timeout: 2000 });
      try { await response.locator('img').first().waitFor({ state: 'attached', timeout: 1500 }); }
      catch { updates.push({ index: f.index, status: 'result-not-loaded' }); continue; }
      const urls = await response.locator('img').evaluateAll(es => es.map(im => im.getAttribute('data-src') || im.src)
        .filter(u => /^https?:\/\//.test(u || '') && !/gen_loading|\.gif(?:[?#]|$)/i.test(u)));
      if (!urls.length) { updates.push({ index: f.index, status: 'generating' }); continue; }
      if (urls.length !== 1) throw new Error('Expected one result for frame ' + f.index);
      ready.push({ frame: f, url: urls[0] });
    }
    let cursor = 0;
    const prepared = [];
    const downloader = async () => {
      while (cursor < ready.length) {
        const { frame: f, url } = ready[cursor++], target = path.join(output, f.outputName);
        try {
          let bytes, existing = false;
          try {
            bytes = await fs.readFile(target);
            if (!f.expectedSha256 || sha256(bytes) !== f.expectedSha256) throw new Error('Existing output conflicts: ' + f.outputName);
            existing = true;
          } catch (error) {
            if (error.code !== 'ENOENT') throw error;
            const res = await fetch(url, { signal: AbortSignal.timeout(timing.downloadMs) });
            if (!res.ok) throw new Error('Download HTTP ' + res.status);
            const mime = (res.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
            bytes = Buffer.from(await res.arrayBuffer());
            if (mime !== 'image/png' || !bytes.subarray(0, 8).equals(pngSignature)) throw new Error('Result is not a PNG.');
            if (f.expectedSha256 && sha256(bytes) !== f.expectedSha256) throw new Error('Downloaded content changed after checkpoint: ' + f.outputName);
          }
          prepared.push({ f, url, target, bytes, existing });
        } catch (error) {
          f.downloadError = String(error.message).slice(0, 200);
          updates.push({ index: f.index, status: 'download-failed', reason: f.downloadError });
        }
      }
    };
    // Fetch in parallel, checkpoint all hashes, then commit files without overwriting any target.
    await Promise.all(Array.from({ length: Math.min(Math.max(1, downloadConcurrency), ready.length) }, downloader));
    for (const { f, url, bytes } of prepared) Object.assign(f, { resultUrl: url, expectedSha256: sha256(bytes) });
    await save();
    if (prepared.length) await fs.mkdir(output, { recursive: true });
    for (const { f, url, target, bytes, existing } of prepared) {
      try {
        if (!existing) {
          const temp = target + '.part-' + randomUUID();
          try { await fs.writeFile(temp, bytes, { flag: 'wx' }); await fs.link(temp, target); }
          finally { await fs.unlink(temp).catch(() => {}); }
        }
        Object.assign(f, { resultUrl: url, saved: target, bytes: bytes.length,
          completedAt: new Date().toISOString(), downloadError: null });
        updates.push({ index: f.index, saved: target });
      } catch (error) {
        f.downloadError = String(error.message).slice(0, 200);
        updates.push({ index: f.index, status: 'download-failed', reason: f.downloadError });
      }
    }
    await save();
    return { ...summary(), updates: updates.sort((a, b) => a.index - b.index) };
  }

  const api = {
    stage: (i, opts) => exclusive(() => stageFrame(i, opts)), submit: i => exclusive(() => submitFrame(i)),
    retryUpload: i => exclusive(() => retryUploadFrame(i)), collect: opts => exclusive(() => collectFrames(opts)),
    reconcile: i => exclusive(() => reconcileFrame(frameAt(i))), status: () => exclusive(async () => summary()),
    summary: () => exclusive(async () => summary()),
    approveFirstFrame: i => exclusive(async () => {
      const f = frameAt(i);
      if (f !== manifest.frames[0] || !f.saved) throw new Error('Inspect the saved first result before approving.');
      manifest.firstFrameApproved = true; await save(); return summary();
    }),
    resumeAfterRestart: () => exclusive(async () => {
      if (await page.locator(s.stack).count() || (await page.locator(s.editor).innerText()).trim()) throw new Error('Restart recovery needs an empty composer.');
      for (const f of manifest.frames.filter(f => !f.saved)) {
        const found = await reconcileFrame(frameAt(f.index));
        if (!found.found && (f.messageId || ['submitting', 'uncertain'].includes(f.submissionState))) {
          throw new Error('Uncertain/missing submitted task. Load history; never reset it as unsubmitted.');
        }
      }
      if ((manifest.restartCount || 0) >= 2) throw new Error('Automatic restart limit reached; diagnose before trying more.');
      manifest.restartCount = (manifest.restartCount || 0) + 1;
      for (const f of manifest.frames.filter(f => !f.messageId)) {
        Object.assign(f, { submissionState: 'planned', uploadRetries: 0, uploadFailureRecorded: false });
      }
      manifest.composerIndex = null; manifest.consecutiveUploadFailures = 0; manifest.recoveryRequired = null;
      await save(); return summary();
    }),
    pump: ({ maxSubmissions = 4, budgetMs = 35000, maxInFlight = Infinity, collect = false } = {}) => exclusive(async () => {
      if (budgetMs > 45000 || budgetMs < 1 || maxSubmissions < 1) throw new Error('Use a 1–45000 ms pump budget and positive submission count.');
      const deadline = Date.now() + budgetMs, updates = [];
      let submitted = 0;
      while (Date.now() < deadline && submitted < maxSubmissions) {
        if (manifest.recoveryRequired) return { ...summary(), status: manifest.recoveryRequired.action, updates };
        if (!manifest.firstFrameApproved && manifest.frames[0].messageId) {
          const collected = collect ? await collectFrames() : null;
          return { ...summary(), status: 'first-frame-review', updates, ...(collected ? { collected } : {}) };
        }
        if (manifest.frames.filter(f => f.messageId && !f.saved && !f.generationError).length >= maxInFlight) break;
        const f = manifest.composerIndex ? frameAt(manifest.composerIndex) : manifest.frames.find(f => !f.messageId);
        if (!f) break;
        const staged = await stageFrame(f.index, { waitMs: Math.min(timing.uploadWaitMs, Math.max(1, deadline - Date.now())) });
        if (staged.status === 'upload-failed') { updates.push(staged, await retryUploadFrame(f.index)); continue; }
        if (['restart-required', 'needs-attention'].includes(staged.status)) return { ...summary(), status: staged.status, updates: [...updates, staged] };
        if (staged.status === 'uploading') { updates.push(staged); continue; }
        const result = staged.alreadySubmitted ? staged : await submitFrame(f.index);
        updates.push(result); submitted++;
        if (result.inspectComposerBeforeNextFrame) break;
      }
      const collected = collect ? await collectFrames() : null;
      return { ...summary(), status: manifest.frames.every(f => f.messageId) ? 'all-submitted' : 'continue', updates,
        ...(collected ? { collected } : {}) };
    }),
    detach: () => {
      if (busy && !page.isClosed()) throw new Error('Wait for the operation before detaching.');
      lease.closed = true;
      if (sessions.get(manifestPath) === lease) sessions.delete(manifestPath);
      if (pageOwners.get(page) === lease) pageOwners.delete(page);
    },
  };
  lease.api = api; sessions.set(manifestPath, lease); pageOwners.set(page, lease);
  try { await save(); } catch (error) { api.detach(); throw error; }
  return api;
}
module.exports = { connect, openBatch };
