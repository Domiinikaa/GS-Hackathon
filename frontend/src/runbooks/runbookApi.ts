// OSOBA 4 – wywołania backendu dla runbooków i testu silnika (routers/runbooks.py).
import { api } from '../shared/api';
import type { Alert, Runbook, RunbookStep, StepKind } from '../shared/types';

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

// symulator systemów docelowych (services/simulator.py)
export interface SimService {
  name: string;
  healthy: boolean;
  workflows_ok: boolean;          // czy ponowienie procesu się uda (settlement)
  restarting: boolean;
  restarting_until: string | null;
}

export interface SimCall {
  id: number;
  service: string | null;
  action: string;
  detail: string | null;
  ok: boolean;
  alert_id: number | null;
  at: string;
}

// akcje, które aplikacja umie wykonać: wbudowane i własne zespołu (Runbooks → Actions)
export interface BuiltinAction { key: string; label: string; risky: boolean }
export interface CustomAction { id: number; key: string; label: string; url: string; risky: boolean; description: string | null }
export interface CustomActionIn { label: string; url: string; risky: boolean; description?: string | null }

// rodzaj każdego kroku: wybrany ręcznie albo null = wykryj automatycznie
export type StepKinds = (StepKind | null)[];

const json = (body: unknown) => ({ body: JSON.stringify(body) });

export const runbookApi = {
  list: () => api<Runbook[]>('/runbooks'),
  parse: (raw: string, format: RunbookFormat) =>
    api<ParseResult>('/runbooks/parse', { method: 'POST', ...json({ raw, format }) }),
  create: (name: string, raw: string, format: RunbookFormat, kinds?: StepKinds) =>
    api<Runbook>('/runbooks', { method: 'POST', ...json({ name, raw, format, kinds }) }),
  update: (id: number, name: string, raw: string, format: RunbookFormat, kinds?: StepKinds) =>
    api<Runbook>(`/runbooks/${id}`, { method: 'PUT', ...json({ name, raw, format, kinds }) }),
  remove: (id: number) => api<{ deleted: number }>(`/runbooks/${id}`, { method: 'DELETE' }),
  attach: (id: number, ruleId: string) => api(`/runbooks/${id}/attach/${ruleId}`, { method: 'POST' }),
  detach: (id: number, ruleId: string) => api(`/runbooks/${id}/attach/${ruleId}`, { method: 'DELETE' }),
  rules: () => api<RuleRef[]>('/rules'),
  testEngine: (event: unknown) => api<EngineResult>('/engine/test', { method: 'POST', ...json({ event }) }),

  // Retry nieudanego kroku w alercie (Approve i Mark done są w alertach – Osoba 1); stepIndex liczony od 0
  retryStep: (alertId: number, stepIndex: number) =>
    api<Alert>(`/alerts/${alertId}/steps/${stepIndex}/retry`, { method: 'POST' }),

  actions: () => api<{ builtin: BuiltinAction[]; custom: CustomAction[] }>('/actions'),
  createAction: (a: CustomActionIn) => api<CustomAction>('/actions', { method: 'POST', ...json(a) }),
  updateAction: (id: number, a: CustomActionIn) => api<CustomAction>(`/actions/${id}`, { method: 'PUT', ...json(a) }),
  removeAction: (id: number) => api<{ deleted: number }>(`/actions/${id}`, { method: 'DELETE' }),

  simServices: () => api<SimService[]>('/sim/services'),
  setSimService: (name: string, patch: Partial<Pick<SimService, 'healthy' | 'workflows_ok'>>) =>
    api<SimService>(`/sim/services/${name}`, { method: 'PUT', ...json(patch) }),
  simCalls: (limit = 20) => api<SimCall[]>(`/sim/calls?limit=${limit}`),
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
