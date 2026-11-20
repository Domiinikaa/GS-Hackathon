// OSOBA 4 – wywołania backendu dla runbooków i testu silnika (routers/runbooks.py).
import { api } from '../shared/api';
import type { Runbook, RunbookStep } from '../shared/types';

export type RunbookFormat = 'auto' | 'yaml' | 'markdown' | 'text' | 'link';

export interface RuleRef {
  id: string;
  name: string;
  team: string;
  runbook_id: number | null;
}

export interface EngineMatch {
  rule_id: string;
  team: string;
  dedup_key: string;
  title: string;
  body: string | null;
  severity: string;
  color: string;
  channels: string[];
  steps: RunbookStep[];
}

export interface EngineResult {
  checked: string[];
  matched: EngineMatch[];
  not_matched: string[];
}

const json = (body: unknown) => ({ body: JSON.stringify(body) });

export const runbookApi = {
  list: () => api<Runbook[]>('/runbooks'),
  parse: (raw: string, format: RunbookFormat) =>
    api<{ format: string; steps: RunbookStep[] }>('/runbooks/parse', { method: 'POST', ...json({ raw, format }) }),
  create: (name: string, raw: string, format: RunbookFormat) =>
    api<Runbook>('/runbooks', { method: 'POST', ...json({ name, raw, format }) }),
  update: (id: number, name: string, raw: string, format: RunbookFormat) =>
    api<Runbook>(`/runbooks/${id}`, { method: 'PUT', ...json({ name, raw, format }) }),
  remove: (id: number) => api<{ deleted: number }>(`/runbooks/${id}`, { method: 'DELETE' }),
  attach: (id: number, ruleId: string) => api(`/runbooks/${id}/attach/${ruleId}`, { method: 'POST' }),
  detach: (id: number, ruleId: string) => api(`/runbooks/${id}/attach/${ruleId}`, { method: 'DELETE' }),
  rules: () => api<RuleRef[]>('/rules'),
  testEngine: (event: unknown) => api<EngineResult>('/engine/test', { method: 'POST', ...json({ event }) }),
};

// Backend zwraca błąd jako "422 {"detail":"..."}" – wyciągamy samą treść
export function errorText(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e);
  const m = msg.match(/^\d+\s+(\{.*\})$/s);
  if (m) {
    try {
      const detail = JSON.parse(m[1]).detail;
      return typeof detail === 'string' ? detail : JSON.stringify(detail);
    } catch { /* zostaw oryginał */ }
  }
  return msg;
}
