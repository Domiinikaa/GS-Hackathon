// Rule conditions as a bullet list; nested groups are indented.
import { Condition, ConditionNode, OPERATORS, isLeaf } from './ruleTypes';

function formatValue(value: Condition['value']): string {
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'number') return value.toLocaleString('en-US');
  return value;
}

function ConditionLine({ c }: { c: Condition }) {
  const phrase = OPERATORS.find((o) => o.value === c.op)?.phrase ?? c.op;
  return (
    <span>
      <span className="font-mono text-slate-200">{c.field}</span>{' '}
      <span className="text-slate-400">{phrase}</span>{' '}
      <span className="font-mono text-amber-200">{formatValue(c.value)}</span>
    </span>
  );
}

function Group({ items }: { items: ConditionNode[] }) {
  return (
    <ul className="list-disc pl-5 space-y-0.5 marker:text-slate-600">
      {items.map((node, i) => (
        <li key={i}>
          {isLeaf(node) ? (
            <ConditionLine c={node} />
          ) : (
            <>
              <span className="text-xs font-semibold text-slate-400">{'and' in node ? 'ALL' : 'ANY'} of these:</span>
              <Group items={'and' in node ? node.and : node.or} />
            </>
          )}
        </li>
      ))}
      {items.length === 0 && <li className="text-slate-500">no conditions</li>}
    </ul>
  );
}

export default function RuleConditions({ condition }: { condition: { and: ConditionNode[] } | { or: ConditionNode[] } }) {
  const mode = 'and' in condition ? 'and' : 'or';
  const items = 'and' in condition ? condition.and : condition.or;
  return (
    <div className="text-sm">
      <p className="text-slate-400">
        When <b className="text-slate-200">{mode === 'and' ? 'ALL' : 'ANY'}</b> of these match:
      </p>
      <Group items={items} />
    </div>
  );
}
