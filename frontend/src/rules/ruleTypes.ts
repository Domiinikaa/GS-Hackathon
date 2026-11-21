// Rule types.

export type Operator = 'eq' | 'neq' | 'gt' | 'gte' | 'lt' | 'lte' | 'in' | 'contains' | 'wildcard';
export type Channel = 'email' | 'sms' | 'phone' | 'ui';
export type Severity = 'info' | 'warning' | 'critical';
export type Color = 'red' | 'amber' | 'blue' | 'green' | 'slate';

// One condition, e.g. { field: "payload.notional", op: "gt", value: 10000000 }
export interface Condition {
  field: string;
  op: Operator;
  value: string | number | string[];
}

// A node is a single condition or a nested and / or / not group
export type ConditionNode =
  | Condition
  | { and: ConditionNode[] }
  | { or: ConditionNode[] }
  | { not: ConditionNode };

// Top level: "and" = all must match, "or" = any one is enough
export type ConditionGroup = { and: ConditionNode[] } | { or: ConditionNode[] };

export interface Rule {
  id: string;
  name: string;
  team: string;
  enabled: boolean;
  condition: ConditionGroup;
  channels: Channel[];
  title: string;           // title template, e.g. "Rejected {{payload.currency}}"
  body?: string | null;           // body template
  severity: Severity;
  color: Color;
  group_by?: string | null;       // e.g. "instrument" – group alerts by this field
  group_window_s?: number | null; // e.g. 300 = one alert per 5 minutes
  runbook_id?: number | null;
  updated_at?: string | null;
}

// phrase = how the operator reads in the condition sentence; types = field types it makes sense for
export const OPERATORS: { value: Operator; label: string; symbol: string; phrase: string; types: FieldKind[] }[] = [
  { value: 'eq', label: 'equals', symbol: '=', phrase: 'is', types: ['text', 'number'] },
  { value: 'neq', label: 'not equals', symbol: '≠', phrase: 'is not', types: ['text', 'number'] },
  { value: 'gt', label: 'greater than', symbol: '>', phrase: 'is greater than', types: ['number'] },
  { value: 'gte', label: 'greater or equal', symbol: '≥', phrase: 'is at least', types: ['number'] },
  { value: 'lt', label: 'less than', symbol: '<', phrase: 'is less than', types: ['number'] },
  { value: 'lte', label: 'less or equal', symbol: '≤', phrase: 'is at most', types: ['number'] },
  { value: 'in', label: 'is one of', symbol: 'in', phrase: 'is one of', types: ['text', 'number'] },
  { value: 'contains', label: 'contains text', symbol: 'contains', phrase: 'contains', types: ['text'] },
  { value: 'wildcard', label: 'matches pattern', symbol: 'matches', phrase: 'matches pattern (*)', types: ['text'] },
];

export type FieldKind = 'text' | 'number';

// Operators that make sense for a field type; unknown fields get all of them
export function operatorsFor(kind: FieldKind | null) {
  return kind ? OPERATORS.filter((o) => o.types.includes(kind)) : OPERATORS;
}

export const CHANNELS: { value: Channel; label: string }[] = [
  { value: 'email', label: 'Email' },
  { value: 'sms', label: 'SMS' },
  { value: 'phone', label: 'Phone call' },
  { value: 'ui', label: 'UI' },
];

export const SEVERITIES: Severity[] = ['info', 'warning', 'critical'];

export const COLORS: Color[] = ['red', 'amber', 'blue', 'green', 'slate'];

// Urgency levels shown in the rule form. The alert colour follows the urgency,
// so users pick one meaningful thing instead of a colour and a severity separately.
export const SEVERITY_OPTIONS: { value: Severity; label: string; hint: string; color: Color }[] = [
  { value: 'critical', label: 'Critical', hint: 'Act now – something is broken', color: 'red' },
  { value: 'warning', label: 'Warning', hint: 'Look soon – something is wrong', color: 'amber' },
  { value: 'info', label: 'Info', hint: 'Good to know – no action needed', color: 'blue' },
];

export function colorForSeverity(severity: Severity): Color {
  return SEVERITY_OPTIONS.find((o) => o.value === severity)?.color ?? 'amber';
}

// Tailwind needs full class names written in the code, hence this map
export const COLOR_DOT: Record<Color, string> = {
  red: 'bg-red-500',
  amber: 'bg-amber-500',
  blue: 'bg-blue-500',
  green: 'bg-emerald-500',
  slate: 'bg-slate-500',
};

// Whether the top-level group is AND or OR, and its items
export function groupMode(group: ConditionGroup): 'and' | 'or' {
  return 'and' in group ? 'and' : 'or';
}

export function groupItems(group: ConditionGroup): ConditionNode[] {
  return 'and' in group ? group.and : group.or;
}

export function isLeaf(node: ConditionNode): node is Condition {
  return 'field' in node;
}

// True when the rule has no nested groups, so the simple form can edit it
export function isFlat(group: ConditionGroup): boolean {
  return groupItems(group).every(isLeaf);
}
