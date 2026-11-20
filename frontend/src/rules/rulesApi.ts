// Backend calls for rules and rule-editor suggestions.
import { api } from '../shared/api';
import type { Channel, Rule, Severity } from './ruleTypes';

export interface FieldHint {
  field: string;     // e.g. "payload.notional"
  example: unknown;  // sample value from a real event
  count: number;
}

export interface PlannedRecipient {
  person_id: number | null;
  name: string;
  channel: Channel;
  to: string | null;
  reason: string;
}

const json = (body: unknown): RequestInit['body'] => JSON.stringify(body);

export const rulesApi = {
  list: () => api<Rule[]>('/rules'),
  create: (rule: Rule) => api<Rule>('/rules', { method: 'POST', body: json({ ...rule, id: rule.id || undefined }) }),
  update: (rule: Rule) => api<Rule>(`/rules/${encodeURIComponent(rule.id)}`, { method: 'PUT', body: json(rule) }),
  setEnabled: (id: string, enabled: boolean) =>
    api<Rule>(`/rules/${encodeURIComponent(id)}`, { method: 'PATCH', body: json({ enabled }) }),
  remove: (id: string) =>
    api<{ deleted: boolean; disabled?: boolean; detail?: string }>(`/rules/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  fields: () => api<FieldHint[]>('/rules/fields'),
  teams: () => api<{ teams: string[]; people: string[] }>('/people/teams'),
  previewRecipients: (team: string, severity: Severity, channels: Channel[]) =>
    api<PlannedRecipient[]>('/people/preview', { method: 'POST', body: json({ team, severity, channels }) }),
};

// Backend error ("422 {"detail":[...]}") -> readable sentence for the user
export function errorMessage(err: unknown): string {
  const text = err instanceof Error ? err.message : String(err);
  const jsonStart = text.indexOf('{');
  if (jsonStart >= 0) {
    try {
      const detail = JSON.parse(text.slice(jsonStart)).detail;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) {
        return detail
          .map((d: { loc?: (string | number)[]; msg?: string }) =>
            `${(d.loc ?? []).filter((p) => p !== 'body').join('.')}: ${(d.msg ?? '').replace(/^Value error, /, '')}`)
          .join('; ');
      }
    } catch {
      /* plain text */
    }
  }
  return text;
}
