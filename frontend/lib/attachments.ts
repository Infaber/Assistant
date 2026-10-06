import type { LocalParticipant } from 'livekit-client';

export const MAX_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_FILES = 3;
export const ACCEPT_FILES = '.png,.jpg,.jpeg,.webp,.gif,.pdf,.docx,.txt,.md,.csv,.json,.py,.js,.ts,.tsx,.html,.css,.yaml,.yml,.log';
const extensions = new Set(ACCEPT_FILES.split(','));
export function validateFiles(files: Pick<File, 'name' | 'size'>[], existing = 0) {
  if (files.length + existing > MAX_FILES) throw new Error('Attach up to three files per message.');
  for (const file of files) {
    const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    if (!extensions.has(extension)) throw new Error(`${file.name}: use a picture, PDF, DOCX or text/code file.`);
    if (!file.size || file.size > MAX_FILE_BYTES) throw new Error(`${file.name}: files must be nonempty and at most 10 MB.`);
  }
}
export type AttachmentBatch = { requestId: string; files: File[]; question: string; ids: string[]; committing: boolean };
type Sender = Pick<LocalParticipant, 'sendFile' | 'performRpc'>;
export async function sendAttachments(sender: Sender, destination: string, batch: AttachmentBatch, progress: (value: number) => void) {
  validateFiles(batch.files);
  for (let index = batch.ids.length; index < batch.files.length; index++) {
    const info = await sender.sendFile(batch.files[index], { topic: 'ariana.attachments', destinationIdentities: [destination], onProgress: value => progress((index + value) / batch.files.length) });
    batch.ids.push(info.id);
  }
  batch.committing = true;
  const response = await sender.performRpc({ destinationIdentity: destination, method: 'ariana.attachments.commit', responseTimeout: 15_000, payload: JSON.stringify({ request_id: batch.requestId, ids: batch.ids, question: batch.question }) });
  const receipt = JSON.parse(response);
  if (receipt.error) { batch.committing = false; throw new Error(receipt.error); }
  if (receipt.accepted !== true || receipt.request_id !== batch.requestId) throw new Error('No valid receipt received. Retry to check whether Ariana accepted your message.');
}
