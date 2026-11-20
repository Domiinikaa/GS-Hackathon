// Typy reguł.
// UWAGA: to wersja robocza – format trzeba jeszcze ustalić z Osobą 3 (backend) i Osobą 4 (silnik reguł).

export type Operator = 'eq' | 'neq' | 'gt' | 'gte' | 'lt' | 'lte' | 'in' | 'contains' | 'wildcard';
export type Channel = 'email' | 'sms' | 'phone' | 'ui';
export type Severity = 'info' | 'warning' | 'critical';
export type Color = 'red' | 'amber' | 'blue' | 'green' | 'slate';

// Jeden warunek, np. { field: "payload.notional", op: "gt", value: 10000000 }
export interface Condition {
  field: string;
  op: Operator;
  value: string | number | string[];
}

// Grupa warunków: "and" = muszą być spełnione wszystkie, "or" = wystarczy jeden
export type ConditionGroup = { and: Condition[] } | { or: Condition[] };

export interface Rule {
  id: string;
  name: string;
  team: string;
  enabled: boolean;
  condition: ConditionGroup;
  channels: Channel[];
  title: string;           // szablon tytułu, np. "Rejected {{payload.currency}}"
  body?: string | null;           // szablon treści
  severity: Severity;
  color: Color;
  group_by?: string | null;       // np. "instrument" – grupuj alerty po tym polu
  group_window_s?: number | null; // np. 300 = jeden alert na 5 minut
  runbook_id?: number | null;
  updated_at?: string | null;
}

export const OPERATORS: { value: Operator; label: string; symbol: string }[] = [
  { value: 'eq', label: 'equals', symbol: '=' },
  { value: 'neq', label: 'not equals', symbol: '≠' },
  { value: 'gt', label: 'greater than', symbol: '>' },
  { value: 'gte', label: 'greater or equal', symbol: '≥' },
  { value: 'lt', label: 'less than', symbol: '<' },
  { value: 'lte', label: 'less or equal', symbol: '≤' },
  { value: 'in', label: 'is one of (comma separated)', symbol: 'in' },
  { value: 'contains', label: 'contains text', symbol: 'contains' },
  { value: 'wildcard', label: 'matches pattern (use *)', symbol: 'matches' },
];

export const CHANNELS: { value: Channel; label: string }[] = [
  { value: 'email', label: 'Email' },
  { value: 'sms', label: 'SMS' },
  { value: 'phone', label: 'Phone call' },
  { value: 'ui', label: 'UI' },
];

export const SEVERITIES: Severity[] = ['info', 'warning', 'critical'];

export const COLORS: Color[] = ['red', 'amber', 'blue', 'green', 'slate'];

// Tailwind wymaga pełnych nazw klas wpisanych w kodzie, dlatego taka mapa
export const COLOR_DOT: Record<Color, string> = {
  red: 'bg-red-500',
  amber: 'bg-amber-500',
  blue: 'bg-blue-500',
  green: 'bg-emerald-500',
  slate: 'bg-slate-500',
};

// Pomocnicze: czy grupa to AND czy OR, i jakie ma warunki
export function groupMode(group: ConditionGroup): 'and' | 'or' {
  return 'and' in group ? 'and' : 'or';
}

export function groupConditions(group: ConditionGroup): Condition[] {
  return 'and' in group ? group.and : group.or;
}
