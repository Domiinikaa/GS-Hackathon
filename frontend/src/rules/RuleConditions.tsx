// Rule conditions as list cells: field on the left, "is greater than 10,000,000" on the right.
import { Condition, ConditionGroup, ConditionNode, OPERATORS, isLeaf } from './ruleTypes';

export function formatValue(value: Condition['value']): string {
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'number') return value.toLocaleString('en-US');
  return value;
}

export function operatorSymbol(op: Condition['op']): string {
  return OPERATORS.find((o) => o.value === op)?.symbol ?? op;
}

function phrase(op: Condition['op']): string {
  return OPERATORS.find((o) => o.value === op)?.phrase ?? op;
}

function Rows({ nodes, depth }: { nodes: ConditionNode[]; depth: number }) {
  return (
    <>
      {nodes.map((node, i) => {
        if (isLeaf(node)) {
          return (
            <div key={i} className="ios-row items-baseline" style={{ paddingLeft: 16 + depth * 20 }}>
              <code className="font-mono text-[13px] text-white break-all">{node.field}</code>
              <span className="ml-auto text-right text-[15px] text-ink-muted">
                {phrase(node.op)} <span className="text-white font-medium">{formatValue(node.value)}</span>
              </span>
            </div>
          );
        }
        const title = 'not' in node ? 'None of these' : 'and' in node ? 'All of these' : 'Any of these';
        const children = 'not' in node ? [node.not] : 'and' in node ? node.and : node.or;
        return (
          <div key={i} className="ios-divided">
            <div className="ios-row text-[13px] text-ink-muted" style={{ paddingLeft: 16 + depth * 20, minHeight: 36 }}>{title}</div>
            <Rows nodes={children} depth={depth + 1} />
          </div>
        );
      })}
    </>
  );
}

/** Condition cells; place inside an .ios-group or a .surface-well. */
export default function RuleConditions({ condition }: { condition: ConditionGroup }) {
  const nodes = 'and' in condition ? condition.and : condition.or;
  if (nodes.length === 0) return <div className="ios-row text-ink-muted">No conditions: every event matches.</div>;
  return <div><Rows nodes={nodes} depth={0} /></div>;
}

/** Short plain-words text for one top-level condition, e.g. "desk = rates". */
export function conditionText(node: ConditionNode): string {
  if (isLeaf(node)) return `${node.field} ${operatorSymbol(node.op)} ${formatValue(node.value)}`;
  if ('not' in node) return 'not: ' + conditionText(node.not);
  const inner = 'and' in node ? node.and : node.or;
  return `${'and' in node ? 'all' : 'any'} of ${countConditions(inner)}`;
}

/** Number of leaf conditions. */
export function countConditions(nodes: ConditionNode[]): number {
  return nodes.reduce(
    (sum, n) =>
      sum + (isLeaf(n) ? 1 : 'not' in n ? countConditions([n.not]) : countConditions('and' in n ? n.and : n.or)),
    0,
  );
}
