// OSOBA 4 – wywołania backendu dla runbooków i testu silnika (routers/runbooks.py).
import { api } from '../shared/api';
import type { Runbook, RunbookStep } from '../shared/types';

export type RunbookFormat = 'auto' | 'yaml' | 'json' | 'html' | 'markdown' | 'text' | 'link';

// grupa warunków (jak w regułach): do jakich zdarzeń runbook pasuje sam z siebie
export interface MatchGroup {
  and?: { field: string; op: string; value: unknown }[];
  or?: { field: string; op: string; value: unknown }[];
}

export interface ParseResult {
  format: string;
  steps: RunbookStep[];
  warnings: string[];
  name: string | null;
  matches: MatchGroup | null;
}

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
    api<ParseResult>('/runbooks/parse', { method: 'POST', ...json({ raw, format }) }),
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

// {"and": [{field: "type", op: "eq", value: "WORKFLOW_FAILED"}]} -> 'type = WORKFLOW_FAILED'
export function describeMatches(m: MatchGroup | null | undefined): string {
  if (!m) return '';
  const conds = m.and ?? m.or ?? [];
  const sym: Record<string, string> = { eq: '=', neq: '≠', gt: '>', gte: '≥', lt: '<', lte: '≤', in: 'in', contains: 'contains', wildcard: 'matches' };
  const text = conds.map((c) => `${c.field} ${sym[c.op] ?? c.op} ${Array.isArray(c.value) ? c.value.join(', ') : String(c.value)}`);
  return text.join(m.or ? ' or ' : ' and ');
}

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
