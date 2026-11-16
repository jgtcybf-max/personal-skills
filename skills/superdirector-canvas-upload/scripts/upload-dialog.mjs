import { readFile } from 'node:fs/promises';
import { win32 } from 'node:path';

/**
 * Fill one observed native Open-dialog filename field and verify its text.
 * Accepts a materials/queue plan's explicit batch. Does not press Open, upload,
 * infer UI completion, mark receipts, focus an arbitrary window, or retry.
 */
export async function fillUploadBatch(client, { batch, handle, processId, fieldHandle }) {
  if (!client || typeof client.send !== 'function') throw new Error('Use the current desktop client.');
  if (!batch || !Array.isArray(batch.files) || batch.files.length === 0) throw new Error('An explicit nonempty batch.files array is required.');
  if (![handle, processId, fieldHandle].every(x => Number.isSafeInteger(x) && x > 0)) throw new Error('Pass current observed dialog, process and filename Edit handles.');
  const files = batch.files.map(value => {
    if (typeof value !== 'string' || !win32.isAbsolute(value) || /[\0\r\n"]/.test(value)) throw new Error('Each file must be an exact absolute Windows path without quotes or newlines.');
    const normalized = win32.normalize(value);
    if (!/^[A-Za-z]:\\/.test(normalized) && !/^\\\\[^\\]+\\[^\\]+\\/.test(normalized)) throw new Error('Path must include a drive root or explicit UNC server and share.');
    return normalized;
  });
  if (new Set(files.map(x => x.toLowerCase())).size !== files.length) throw new Error('Duplicate file in batch.');
  // Absolute paths avoid relying on the dialog's previous directory, including
  // adjacent products with identically named angle images.
  const selection = files.map(value => `"${value}"`).join(' ');
  if (selection.length > 30000) throw new Error('Selection too long; split with upload_queue.py.');
  if (batch.selection_file) {
    const saved = (await readFile(batch.selection_file, 'utf8')).replace(/^\uFEFF/, '').trim();
    if (saved !== selection) throw new Error('Selection file differs from batch.files; rebuild or inspect the plan.');
  }
  const response = await client.send({ action: 'nativeText', handle, processId, fieldHandle, text: selection });
  if (response.ok !== true || response.detail?.verified !== true || response.detail?.text !== selection) throw new Error('Filename readback mismatch. Observe dialog; do not press Open or retry.');
  return { verified: true, confirmationSent: false, count: files.length,
    names: files.map(value => win32.basename(value)), selection,
    requestId: response.requestId ?? response.id, roundtrip_ms: response.roundtrip_ms ?? null };
}
