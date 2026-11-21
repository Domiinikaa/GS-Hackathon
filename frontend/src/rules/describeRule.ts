// Rule as a plain sentence.
import { CHANNELS, Condition, OPERATORS, Rule, groupConditions, groupMode } from './ruleTypes';

function formatValue(value: Condition['value']): string {
  if (Array.isArray(value)) return `[${value.join(', ')}]`;
  if (typeof value === 'number') return value.toLocaleString('en-US');
  return `"${value}"`;
}

export function describeCondition(c: Condition): string {
  const symbol = OPERATORS.find((o) => o.value === c.op)?.symbol ?? c.op;
  return `${c.field || '(field)'} ${symbol} ${formatValue(c.value)}`;
}

export function describeRule(rule: Rule): string {
  const channelNames = rule.channels
    .map((ch) => CHANNELS.find((c) => c.value === ch)?.label ?? ch)
    .join(' + ');
  const joiner = groupMode(rule.condition) === 'and' ? ' AND ' : ' OR ';
  const conditions = groupConditions(rule.condition).map(describeCondition).join(joiner);

  let text = `Notify ${rule.team || '(team)'} by ${channelNames || '(no channel)'} when ${conditions || '(no conditions)'}.`;

  if (rule.group_by && rule.group_window_s) {
    const minutes = Math.round(rule.group_window_s / 60);
    text += ` Group into one alert per ${rule.group_by} every ${minutes} min.`;
  }
  return text;
}
