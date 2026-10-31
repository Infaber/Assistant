export type AIMode = 'normal' | 'local';
export type ModeStatus = { mode: AIMode; model: string; state: 'connecting' | 'loading' | 'ready' | 'error'; error: string };
export function parseModeStatus(value: unknown): ModeStatus | null {
  if (!value || typeof value !== 'object') return null;
  const row = value as Record<string, unknown>;
  if (!['normal', 'local'].includes(String(row.mode)) || !['connecting','loading','ready','error'].includes(String(row.state))
    || typeof row.model !== 'string' || row.model.length > 120 || typeof row.error !== 'string' || row.error.length > 500) return null;
  return row as ModeStatus;
}
