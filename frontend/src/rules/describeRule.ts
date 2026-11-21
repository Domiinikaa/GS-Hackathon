// Rule as a plain sentence.
import { CHANNELS, Condition, ConditionNode, OPERATORS, Rule, isLeaf } from './ruleTypes';

function formatValue(value: Condition['value']): string {
  if (Array.isArray(value)) return `[${value.join(', ')}]`;
  if (typeof value === 'number') return value.toLocaleString('en-US');
  return `"${value}"`;
}

export function describeCondition(c: Condition): string {
  const symbol = OPERATORS.find((o) => o.value === c.op)?.symbol ?? c.op;
  return `${c.field || '(field)'} ${symbol} ${formatValue(c.value)}`;
}

// Nested groups are wrapped in brackets, e.g. (a = 1 AND b = 2) OR NOT c = 3
export function describeNode(node: ConditionNode, nested = false): string {
  if (isLeaf(node)) return describeCondition(node);
  if ('not' in node) return `NOT ${describeNode(node.not, true)}`;
  const [items, joiner] = 'and' in node ? [node.and, ' AND '] : [node.or, ' OR '];
  const text = items.map((n) => describeNode(n, true)).join(joiner);
  return nested && items.length > 1 ? `(${text})` : text;
}

export function describeRule(rule: Rule): string {
  const channelNames = rule.channels
    .map((ch) => CHANNELS.find((c) => c.value === ch)?.label ?? ch)
    .join(' + ');
  const conditions = describeNode(rule.condition);

  let text = `Notify ${rule.team || '(team)'} by ${channelNames || '(no channel)'} when ${conditions || '(no conditions)'}.`;

  if (rule.group_by && rule.group_window_s) {
    const minutes = Math.round(rule.group_window_s / 60);
    text += ` Group into one alert per ${rule.group_by} every ${minutes} min.`;
  }
  return text;
}
