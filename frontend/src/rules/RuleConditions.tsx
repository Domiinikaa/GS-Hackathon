// Rule conditions as readable sentences; nested groups hang off a vertical guide line.
import { Condition, ConditionNode, OPERATORS, isLeaf } from './ruleTypes';

function formatValue(value: Condition['value']): string {
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'number') return value.toLocaleString('en-US');
  return value;
}

function ConditionLine({ c }: { c: Condition }) {
  const phrase = OPERATORS.find((o) => o.value === c.op)?.phrase ?? c.op;
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-1.5 gap-y-1">
      <code className="font-mono text-[13px] text-ink">{c.field}</code>
      <span className="text-ink-muted">{phrase}</span>
      <code className="font-mono text-[13px] text-gs-gold break-all">{formatValue(c.value)}</code>
    </span>
  );
}

function Group({ items }: { items: ConditionNode[] }) {
  return (
    <ul className="space-y-2">
      {items.map((node, i) => (
        <li key={i} className="text-sm leading-relaxed">
          {isLeaf(node) ? (
            <ConditionLine c={node} />
          ) : (
            <div>
              <span className="text-[13px] font-medium text-ink-muted">
                {'not' in node ? 'None of these:' : 'and' in node ? 'All of these:' : 'Any of these:'}
              </span>
              <div className="mt-1.5 ml-1 pl-4 border-l border-white/10">
                <Group items={'not' in node ? [node.not] : 'and' in node ? node.and : node.or} />
              </div>
            </div>
          )}
        </li>
      ))}
      {items.length === 0 && <li className="text-sm text-ink-muted">No conditions: every event matches.</li>}
    </ul>
  );
}

export default function RuleConditions({ condition }: { condition: { and: ConditionNode[] } | { or: ConditionNode[] } }) {
  const items = 'and' in condition ? condition.and : condition.or;
  return (
    <div>
      <p className="text-[13px] font-medium text-ink-muted mb-2">
        Matches when {'and' in condition ? 'all' : 'any'} of these are true
      </p>
      <Group items={items} />
    </div>
  );
}

/** Number of leaf conditions, for the collapsed summary. */
export function countConditions(nodes: ConditionNode[]): number {
  return nodes.reduce(
    (sum, n) =>
      sum + (isLeaf(n) ? 1 : 'not' in n ? countConditions([n.not]) : countConditions('and' in n ? n.and : n.or)),
    0,
  );
}
