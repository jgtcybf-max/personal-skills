import { writeFile, rename, unlink } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { setTimeout as sleep } from 'node:timers/promises';
import { performance } from 'node:perf_hooks';
import { platform } from 'node:os';

const clients = new Map();
const actions = new Set([
  'status', 'focus', 'nativeFields', 'nativeText', 'click', 'wheel',
  'keys', 'text', 'drag', 'stop', 'screenshot', 'clipboardRead',
]);
const sequenceActions = new Set(['click', 'wheel', 'keys', 'text', 'drag', 'nativeText']);
const prohibitedFields = new Set(['id', 'generate', 'submit', 'confirm', 'paid', 'retry']);

function error(code, message, details = {}) {
  return Object.assign(new Error(message), { code, ...details });
}

async function json(path) {
  // Tiny IPC files: close the Windows read handle before returning to the poll.
  return JSON.parse(readFileSync(path, 'utf8').replace(/^\uFEFF/, ''));
}

async function publish(temporary, destination) {
  // Windows can briefly deny replacement while the helper reads command.json.
  // Only an explicitly failed rename is retried; no published action is resent.
  const deadline = performance.now() + 250;
  while (true) {
    try { await rename(temporary, destination); return; } catch (cause) {
      if (!['EPERM', 'EACCES', 'EBUSY'].includes(cause.code) || performance.now() >= deadline) throw cause;
      await sleep(5);
    }
  }
}

/**
 * Connects to an already-started, time-limited desktop-input.ps1 helper.
 * No process launch, elevation, lifetime extension, or action retry occurs here.
 * Use one instance/caller for a helper. Different processes must not share it.
 *
 * send(action) performs one action. A timeout or helper failure locks the client;
 * readReady()/readPendingReceipt() remain available. Inspect the actual desktop,
 * wait for the matching receipt, then acknowledgeObserved(requestId) explicitly.
 * There is no resubmit-on-timeout shortcut.
 *
 * sequence(actions, { observedStable: true }) is only for up to six already
 * observed, reversible operations in a stable UI. Never include a generation,
 * payment, publish, delete, file-dialog confirmation, or parameter-close + paid
 * click. Coordinates cannot establish whether a click is paid: the caller must
 * keep those actions separate and verify the current UI between them.
 */
export function createDesktopClient(controlDir, { timeoutMs = 10000, pollMs = 20 } = {}) {
  if (typeof controlDir !== 'string' || !controlDir.trim()) throw error('INVALID_DIRECTORY', 'controlDir is required.');
  if (!Number.isFinite(timeoutMs) || timeoutMs < 20 || timeoutMs > 60000) throw error('INVALID_TIMEOUT', 'timeoutMs must be 20–60000.');
  if (!Number.isFinite(pollMs) || pollMs < 5 || pollMs > 1000) throw error('INVALID_POLL', 'pollMs must be 5–1000.');
  const directory = resolve(controlDir);
  const key = platform() === 'win32' ? directory.toLowerCase() : directory;
  if (clients.has(key)) throw error('CLIENT_EXISTS', 'Use the existing client for this controlDir.');
  let closed = false;
  let pending = null;
  let uncertain = null;
  let tail = Promise.resolve();
  const files = { ready: join(directory, 'ready.json'), command: join(directory, 'command.json'), result: join(directory, 'result.json') };

  async function readReady() {
    const ready = await json(files.ready);
    const expiry = Date.parse(ready.expires_at_utc);
    return { ...ready, expires_valid: Number.isFinite(expiry), expired: !Number.isFinite(expiry) || expiry <= Date.now() };
  }

  async function requireReady() {
    if (closed) throw error('CLIENT_CLOSED', 'Client is closed.');
    if (uncertain) throw error('UNCERTAIN_ACTION', 'Inspect the desktop and acknowledge the matching receipt before any further helper command.', { requestId: uncertain.requestId, uncertain: true });
    const ready = await readReady();
    if (ready.ready !== true) throw error('HELPER_NOT_READY', 'Input helper is not ready; no command was written.');
    if (ready.expired) throw error('HELPER_EXPIRED', 'Input helper lifetime expired or expiry is invalid; no command was written.');
    if (ready.physicalPixels !== true) throw error('PIXEL_MODE_UNVERIFIED', 'physicalPixels must be true; no command was written.');
    // Refuse to clobber a request left in flight by an earlier caller.
    let previous;
    try { previous = await json(files.command); } catch (cause) { if (cause.code !== 'ENOENT') throw cause; }
    if (previous) {
      let receipt;
      try { receipt = await json(files.result); } catch (cause) {
        if (cause.code !== 'ENOENT' && !(cause instanceof SyntaxError)) throw cause;
      }
      if (!previous.id || receipt?.id !== previous.id) {
        uncertain = { requestId: previous.id ?? 'unknown', action: previous.action };
        throw error('EXISTING_PENDING_COMMAND', 'An earlier command has no matching receipt; inspect it before continuing.', { requestId: uncertain.requestId, uncertain: true });
      }
    }
    return ready;
  }

  function validate(action) {
    if (!action || typeof action !== 'object' || Array.isArray(action)) throw error('INVALID_ACTION', 'Action must be an object.');
    if (!actions.has(action.action)) throw error('UNSUPPORTED_ACTION', 'Only desktop-input helper actions are supported.');
    for (const field of Object.keys(action)) {
      if (prohibitedFields.has(field.toLowerCase())) throw error('PROHIBITED_FIELD', `Field ${field} is not allowed.`);
    }
    const numeric = {
      click: ['x', 'y'], wheel: ['x', 'y', 'delta'], drag: ['x1', 'y1', 'x2', 'y2'],
      focus: ['handle'], nativeFields: ['handle', 'processId'], nativeText: ['handle', 'processId', 'fieldHandle'],
    }[action.action] ?? [];
    if (numeric.some(field => !Number.isSafeInteger(action[field]))) throw error('INVALID_ACTION_FIELD', 'Coordinates and handles must be explicit safe integers.');
    if (action.action === 'click' && action.count !== undefined && ![1, 2].includes(action.count)) throw error('INVALID_ACTION_FIELD', 'Click count must be 1 or 2.');
    if (action.action === 'click' && action.button !== undefined && !['left', 'right'].includes(action.button)) throw error('INVALID_ACTION_FIELD', 'Click button must be left or right.');
    if (action.action === 'keys' && (typeof action.keys !== 'string' || !action.keys.length)) throw error('INVALID_ACTION_FIELD', 'keys must contain an explicit key sequence.');
    if (['text', 'nativeText'].includes(action.action) && !(typeof action.text === 'string' && action.text.length) && !(typeof action.textFile === 'string' && action.textFile.length)) throw error('INVALID_ACTION_FIELD', 'text or textFile is required.');
    // Clone now so a queued action cannot be modified by its caller later.
    return JSON.parse(JSON.stringify(action));
  }

  function enqueue(work) {
    const result = tail.then(work);
    tail = result.catch(() => {});
    return result;
  }

  async function perform(action) {
    await requireReady();
    const requestId = randomUUID().replaceAll('-', '');
    const command = { ...action, id: requestId };
    const temporary = join(directory, `command.${requestId}.tmp`);
    const started = performance.now();
    // Only a unique temporary file is created before publishing the command.
    await writeFile(temporary, JSON.stringify(command), { encoding: 'utf8', flag: 'wx' });
    pending = { requestId, action: action.action, started };
    try {
      await publish(temporary, files.command);
      while (performance.now() - started < timeoutMs) {
        let reply;
        try { reply = await json(files.result); } catch (readError) {
          if (readError.code !== 'ENOENT' && !(readError instanceof SyntaxError)) throw readError;
        }
        if (reply?.id === requestId) {
          const receipt = { ...reply, requestId, roundtrip_ms: performance.now() - started };
          if (reply.ok !== true) {
            uncertain = { requestId, action: action.action, receipt };
            throw error('HELPER_ACTION_FAILED', reply.error || 'Helper reported action failure; inspect the desktop before continuing.', { requestId, uncertain: true, receipt });
          }
          pending = null;
          return receipt;
        }
        await sleep(pollMs);
      }
      uncertain = { requestId, action: action.action };
      throw error('HELPER_TIMEOUT', 'Helper timed out. No action was retried. Inspect the actual desktop and wait for the matching receipt.', { requestId, uncertain: true });
    } catch (cause) {
      uncertain ??= { requestId, action: action.action };
      if (cause.uncertain) throw cause;
      throw error('HELPER_IO_UNCERTAIN', 'Command publication or receipt read failed. The action may have landed; inspect before continuing.', { requestId, uncertain: true, cause });
    } finally {
      // Do not remove command.json or result.json: a helper may still be acting.
      await unlink(temporary).catch(() => {});
    }
  }

  const client = {
    controlDir: directory,
    readReady,
    get state() { return { closed, uncertain: uncertain ? { requestId: uncertain.requestId, action: uncertain.action } : null, pending: pending ? { requestId: pending.requestId, action: pending.action } : null }; },
    send(action) {
      let copy;
      try { copy = validate(action); } catch (cause) { return Promise.reject(cause); }
      return enqueue(() => perform(copy));
    },
    sequence(items, { observedStable = false } = {}) {
      let copies;
      try {
        if (observedStable !== true) throw error('OBSERVATION_REQUIRED', 'Set observedStable:true only for already-observed reversible operations in a stable UI.');
        if (!Array.isArray(items) || items.length < 1 || items.length > 6) throw error('INVALID_SEQUENCE', 'A sequence contains 1–6 actions.');
        copies = items.map(validate);
        if (copies.some(item => !sequenceActions.has(item.action))) throw error('INVALID_SEQUENCE_ACTION', 'Use send() separately for this action.');
      } catch (cause) { return Promise.reject(cause); }
      return enqueue(async () => {
        const receipts = [];
        for (const action of copies) receipts.push(await perform(action));
        return receipts;
      });
    },
    async readPendingReceipt() {
      const requestId = uncertain?.requestId ?? pending?.requestId;
      if (!requestId) return null;
      let reply;
      try { reply = await json(files.result); } catch (cause) {
        if (cause.code === 'ENOENT' || cause instanceof SyntaxError) return null;
        throw cause;
      }
      return reply.id === requestId ? { ...reply, requestId } : null;
    },
    acknowledgeObserved(requestId) {
      return enqueue(async () => {
        if (!uncertain || uncertain.requestId !== requestId) throw error('ACK_ID_MISMATCH', 'Acknowledge the exact uncertain requestId.');
        const receipt = await client.readPendingReceipt();
        if (!receipt) throw error('RECEIPT_PENDING', 'No matching receipt yet; command remains locked and must not be overwritten.');
        uncertain = null;
        pending = null;
        return { acknowledged: true, requestId, receipt };
      });
    },
    close() {
      return enqueue(async () => {
        if (uncertain || pending) throw error('UNCERTAIN_ACTION', 'Cannot release a client with an unresolved action.');
        closed = true;
        clients.delete(key);
        return { closed: true };
      });
    },
  };
  clients.set(key, client);
  return client;
}
