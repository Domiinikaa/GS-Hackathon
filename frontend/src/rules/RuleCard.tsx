// One rule as an iOS grouped list: header with switch, then label / value cells,
// with the full condition list behind a disclosure row.
import { useId } from 'react';
import { ChevronRight } from 'lucide-react';
import type { Rule } from './ruleTypes';
import RuleConditions, { conditionText, countConditions } from './RuleConditions';
import { Row, SEVERITY_DOT, SeverityBadge, type SeverityLevel, Toggle, cn } from '../shared/ui';

interface Props {
  rule: Rule;
  runbookName?: string;
  open: boolean;
  onToggleOpen: () => void;
  onToggleEnabled: () => void;
  onEdit: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}

export default function RuleCard({ rule, runbookName, open, onToggleOpen, onToggleEnabled, onEdit, onDuplicate, onDelete }: Props) {
  const detailsId = useId();
  const isAnd = 'and' in rule.condition;
  const nodes = 'and' in rule.condition ? rule.condition.and : rule.condition.or;
  const total = countConditions(nodes);
  const summary = nodes.length === 0
    ? 'Every event'
    : nodes.slice(0, 2).map(conditionText).join(isAnd ? ' and ' : ' or ') + (nodes.length > 2 ? ` +${nodes.length - 2} more` : '');

  return (
    <article className={cn('ios-group transition-opacity', !rule.enabled && 'opacity-55')}>
      {/* header */}
      <div className="ios-row py-3.5">
        <span className={cn('w-2.5 h-2.5 rounded-full shrink-0', SEVERITY_DOT[rule.severity as SeverityLevel] ?? 'bg-ink-faint')} aria-hidden="true" />
        <div className="flex-1 min-w-0">
          <h3 className="text-[17px] font-semibold text-white leading-snug">{rule.name}</h3>
          <p className="text-[13px] text-ink-muted">{rule.enabled ? 'Active' : 'Turned off'}</p>
        </div>
        <Toggle checked={rule.enabled} onChange={onToggleEnabled}
          label={rule.enabled ? `Turn off ${rule.name}` : `Turn on ${rule.name}`} />
      </div>

      <Row label="When" value={<span className="font-mono text-[13px] text-white break-words">{summary}</span>} />
      <Row label="Send to" value={<span className="text-white">{rule.team}</span>} />
      <Row label="Notifies" value="Team feed and each person's choice" />
      <Row label="Urgency" value={<SeverityBadge severity={rule.severity} />} />
      {rule.runbook_id && <Row label="Runbook" value={runbookName ?? `#${rule.runbook_id}`} />}

      {/* disclosure: full conditions + headline */}
      <button type="button" onClick={onToggleOpen} aria-expanded={open} aria-controls={detailsId}
        className="ios-row ios-row--tap w-full text-left">
        <span className="flex-1 text-[15px] text-white">Conditions</span>
        <span className="text-[15px] text-ink-muted">{total}</span>
        <ChevronRight className={cn('w-4 h-4 text-ink-faint transition-transform duration-300', open && 'rotate-90')} aria-hidden="true" />
      </button>
      <div id={detailsId} className="disclosure ios-divided" data-open={open}>
        <div {...(open ? {} : ({ inert: '' } as Record<string, string>))}>
          <div className="bg-black/25">
            <div className="ios-row text-[13px] text-ink-muted" style={{ minHeight: 36 }}>
              Matches when {isAnd ? 'all' : 'any'} of these are true
            </div>
            <div className="ios-divided"><RuleConditions condition={rule.condition} /></div>
            <div className="ios-divided">
              <div className="ios-row flex-col items-start gap-1">
                <span className="text-[13px] text-ink-muted">Alert headline</span>
                <code className="font-mono text-[13px] text-white break-all">{rule.title}</code>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* actions */}
      <div className="ios-row justify-between ios-divided">
        <div className="flex items-center gap-4">
          <button type="button" onClick={onEdit} className="text-[15px] text-ios-blue hover:opacity-70">Edit rule</button>
          <button type="button" onClick={onDuplicate} className="text-[15px] text-amber-400 hover:opacity-70">Duplicate</button>
        </div>
        <button type="button" onClick={onDelete} className="text-[15px] text-ios-red hover:opacity-70">Delete</button>
      </div>
    </article>
  );
}
