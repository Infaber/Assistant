export type ActivityStatus = 'running' | 'returned' | 'verified' | 'approval' | 'uncertain' | 'failed' | 'recovering';
export type Activity = { version: 1; id: string; kind: 'action' | 'system'; label: string; status: ActivityStatus; detail: string; timestamp: number };
const statuses = new Set(['running', 'returned', 'verified', 'approval', 'uncertain', 'failed', 'recovering']);

export function parseActivity(bytes: Uint8Array): Activity | null {
  if (bytes.byteLength > 4096) return null;
  try {
    const value = JSON.parse(new TextDecoder().decode(bytes));
    if (!value || value.version !== 1 || !['action', 'system'].includes(value.kind) || !statuses.has(value.status)
      || typeof value.id !== 'string' || !value.id.length || value.id.length > 80
      || typeof value.label !== 'string' || value.label.length > 100
      || typeof value.detail !== 'string' || value.detail.length > 500
      || typeof value.timestamp !== 'number' || !Number.isFinite(value.timestamp) || value.timestamp <= 0) return null;
    return { version: 1, id: value.id, kind: value.kind, label: value.label, status: value.status, detail: value.detail, timestamp: value.timestamp };
  } catch { return null; }
}

export function updateActivity(rows: Activity[], event: Activity): Activity[] {
  const previous = rows.find(row => row.id === event.id);
  if (previous && (previous.timestamp > event.timestamp || (previous.status !== 'running' && event.status === 'running'))) return rows;
  if (previous) return rows.map(row => row.id === event.id ? event : row);
  return [...rows, event].slice(-40);
}

export function finishActivity(rows: Activity[]): Activity[] {
  return rows.map(row => ['running', 'recovering'].includes(row.status) ? { ...row, status: 'uncertain', detail: 'Connection ended before a final result arrived. Check before repeating the action.' } : row);
}
