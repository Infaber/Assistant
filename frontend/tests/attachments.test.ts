import { test } from 'node:test';
import assert from 'node:assert/strict';
import { sendAttachments, validateFiles, MAX_FILE_BYTES, type AttachmentBatch } from '../lib/attachments';

test('validates supported formats, sizes and combined file count', () => {
  validateFiles([{ name: 'picture.PNG', size: 120 }, { name: 'lab.pdf', size: 1000 }]);
  assert.throws(() => validateFiles([{ name: 'archive.zip', size: 5 }]));
  assert.throws(() => validateFiles([{ name: 'big.txt', size: MAX_FILE_BYTES + 1 }]));
  assert.throws(() => validateFiles([{ name: 'empty.txt', size: 0 }]));
  assert.throws(() => validateFiles([{ name: 'lab.txt', size: 20 }], 3));
});

test('a lost receipt retries the same submission without uploading again', async () => {
  let uploads = 0;
  const payloads: string[] = [];
  const sender = {
    sendFile: async () => { uploads++; return { id: 'stream-one' }; },
    performRpc: async (request: { payload: string }) => {
      payloads.push(request.payload);
      if (payloads.length === 1) throw new Error('Connection lost after acceptance');
      return JSON.stringify({ accepted: true, request_id: 'send-one' });
    },
  };
  const batch: AttachmentBatch = { requestId: 'send-one', files: [new File(['Robotics'], 'lab.txt')], question: 'Summarize', ids: [], committing: false };
  await assert.rejects(sendAttachments(sender as never, 'agent', batch, () => {}));
  assert.equal(batch.committing, true);
  await sendAttachments(sender as never, 'agent', batch, () => {});
  assert.equal(uploads, 1);
  assert.equal(payloads[0], payloads[1]);
});

test('an interrupted upload resumes from the files already transferred', async () => {
  let uploads = 0;
  let commits = 0;
  const sender = {
    sendFile: async () => { uploads++; if (uploads === 2) throw new Error('Interrupted'); return { id: `stream-${uploads}` }; },
    performRpc: async () => { commits++; return JSON.stringify({ accepted: true, request_id: 'send-two' }); },
  };
  const batch: AttachmentBatch = { requestId: 'send-two', files: [new File(['one'], 'one.txt'), new File(['two'], 'two.txt')], question: '', ids: [], committing: false };
  await assert.rejects(sendAttachments(sender as never, 'agent', batch, () => {}));
  assert.equal(commits, 0);
  await sendAttachments(sender as never, 'agent', batch, () => {});
  assert.equal(uploads, 3);
  assert.equal(commits, 1);
});
