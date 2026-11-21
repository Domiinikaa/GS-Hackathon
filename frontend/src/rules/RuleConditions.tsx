// Rule conditions as glass chips: [field] [op] [value], joined by AND / OR badges.
import { Fragment } from 'react';
import { Tag } from 'lucide-react';
import { Condition, ConditionGroup, ConditionNode, OPERATORS, isLeaf } from './ruleTypes';

export function formatValue(value: Condition['value']): string {
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'number') return value.toLocaleString('en-US');
  return value;
}

export function operatorSymbol(op: Condition['op']): string {
  return OPERATORS.find((o) => o.value === op)?.symbol ?? op;
}

function ConditionChips({ c }: { c: Condition }) {
  const phrase = OPERATORS.find((o) => o.value === c.op)?.label ?? c.op;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="glass-pill px-2.5 py-1 font-mono text-[12.5px] text-slate-200">
        <Tag className="w-3 h-3 text-ink-muted" aria-hidden="true" />
        {c.field}
      </span>
      <span title={phrase}
        className="px-2.5 py-1 rounded-full bg-white/[0.14] border border-white/20 font-mono text-xs font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.15)]">
        {operatorSymbol(c.op)}
      </span>
      <span className="px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/25 font-mono text-[12.5px] text-amber-200 break-all">
        {formatValue(c.value)}
      </span>
    </div>
  );
}

function Connector({ word }: { word: 'AND' | 'OR' }) {
  return (
    <div className="flex items-center gap-2 py-1.5 pl-3" aria-hidden="true">
      <span className="w-px h-3 bg-white/15" />
      <span className={`text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded-full border ${
        word === 'AND' ? 'text-sky-300 border-sky-500/30 bg-sky-500/10' : 'text-violet-300 border-violet-500/30 bg-violet-500/10'
      }`}>
        {word}
      </span>
    </div>
  );
}

function Node({ node }: { node: ConditionNode }) {
  if (isLeaf(node)) return <ConditionChips c={node} />;
  if ('not' in node) {
    return (
      <div className="flex items-start gap-2">
        <span className="mt-1 text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded-full border text-rose-300 border-rose-500/30 bg-rose-500/10">
          NOT
        </span>
        <div className="flex-1"><Node node={node.not} /></div>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-3">
      <Group group={node} />
    </div>
  );
}

function Group({ group }: { group: ConditionGroup }) {
  const word = 'and' in group ? 'AND' : 'OR';
  const items = 'and' in group ? group.and : group.or;
  if (items.length === 0) return <p className="text-sm text-ink-muted">No conditions: every event matches.</p>;
  return (
    <div>
      {items.map((node, i) => (
        <Fragment key={i}>
          {i > 0 && <Connector word={word} />}
          <Node node={node} />
        </Fragment>
      ))}
    </div>
  );
}

export default function RuleConditions({ condition }: { condition: ConditionGroup }) {
  return <Group group={condition} />;
}

/** Short inline chip for the plain-words summary, e.g. `desk = rates`. */
export function InlineCondition({ node }: { node: ConditionNode }) {
  const text = isLeaf(node)
    ? `${node.field} ${operatorSymbol(node.op)} ${formatValue(node.value)}`
    : 'not' in node
      ? 'a NOT group'
      : `${'and' in node ? 'all' : 'any'} of ${countConditions('and' in node ? node.and : node.or)} conditions`;
  return (
    <code className="inline-block align-baseline px-1.5 py-px mx-0.5 rounded-md bg-white/[0.07] border border-white/10 font-mono text-[12.5px] text-slate-100 break-all">
      {text}
    </code>
  );
}

/** Number of leaf conditions. */
export function countConditions(nodes: ConditionNode[]): number {
  return nodes.reduce(
    (sum, n) =>
      sum + (isLeaf(n) ? 1 : 'not' in n ? countConditions([n.not]) : countConditions('and' in n ? n.and : n.or)),
    0,
  );
}
