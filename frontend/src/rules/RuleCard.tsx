// One rule in the list: a plain-words summary on top, condition chips behind "Show conditions".
import { Fragment, useId } from 'react';
import { ArrowRight, BookOpen, ChevronDown, Pencil, Trash2 } from 'lucide-react';
import type { Rule } from './ruleTypes';
import RuleConditions, { InlineCondition, countConditions } from './RuleConditions';
import { ChannelPill, SeverityBadge, Toggle, cn, iconButton } from '../shared/ui';

const SUMMARY_LIMIT = 3;

interface Props {
  rule: Rule;
  runbookName?: string;
  open: boolean;
  onToggleOpen: () => void;
  onToggleEnabled: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

export default function RuleCard({ rule, runbookName, open, onToggleOpen, onToggleEnabled, onEdit, onDelete }: Props) {
  const detailsId = useId();
  const isAnd = 'and' in rule.condition;
  const nodes = 'and' in rule.condition ? rule.condition.and : rule.condition.or;
  const shown = nodes.slice(0, SUMMARY_LIMIT);
  const hidden = nodes.length - shown.length;
  const total = countConditions(nodes);

  return (
    <article className={cn('glass-card', !rule.enabled && 'opacity-60')}>
      <div className="p-6">
        {/* title row */}
        <div className="flex items-start gap-4">
          <div className="flex-1 min-w-0 flex items-center gap-2 flex-wrap">
            <h3 className="text-[17px] font-semibold leading-snug text-white">{rule.name}</h3>
            <SeverityBadge severity={rule.severity} />
            {rule.runbook_id && (
              <span className="glass-pill px-2.5 py-0.5 text-xs font-medium text-ink">
                <BookOpen className="w-3.5 h-3.5 text-sky-300" aria-hidden="true" />
                Runbook: {runbookName ?? `#${rule.runbook_id}`}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Toggle checked={rule.enabled} onChange={onToggleEnabled}
              label={rule.enabled ? `Turn off ${rule.name}` : `Turn on ${rule.name}`} className="mr-2" />
            <button type="button" onClick={onEdit} title="Edit rule" aria-label={`Edit ${rule.name}`} className={iconButton}>
              <Pencil className="w-4 h-4" />
            </button>
            <button type="button" onClick={onDelete} title="Delete rule" aria-label={`Delete ${rule.name}`}
              className={cn(iconButton, 'hover:text-rose-300 hover:bg-rose-500/10')}>
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* in plain words */}
        <p className="mt-3 text-[15px] leading-8 text-ink-muted">
          When an event has{' '}
          {shown.length === 0 && <span className="text-ink">anything at all</span>}
          {shown.map((node, i) => (
            <Fragment key={i}>
              {i > 0 && <span className="font-semibold text-ink"> {isAnd ? 'and' : 'or'} </span>}
              <InlineCondition node={node} />
            </Fragment>
          ))}
          {hidden > 0 && <span> {isAnd ? 'and' : 'or'} {hidden} more</span>}
          <ArrowRight className="inline w-4 h-4 mx-1.5 -mt-0.5 text-ink-muted" aria-label="then" />
          send via{' '}
          <span className="inline-flex flex-wrap gap-1 align-middle">
            {rule.channels.length > 0
              ? rule.channels.map((c) => <ChannelPill key={c} channel={c} />)
              : <span className="text-ink">no channel</span>}
          </span>{' '}
          to <span className="font-semibold text-white">{rule.team}</span>
        </p>
      </div>

      <button
        type="button"
        onClick={onToggleOpen}
        aria-expanded={open}
        aria-controls={detailsId}
        className="w-full flex items-center justify-between px-6 py-3 border-t border-white/[0.06] text-[13px] font-medium text-ink-muted hover:text-white hover:bg-white/[0.03] rounded-b-2xl transition-colors"
      >
        {open ? 'Hide conditions' : `Show conditions (${total})`}
        <ChevronDown className={cn('w-4 h-4 transition-transform duration-300', open && 'rotate-180')} />
      </button>

      <div id={detailsId} className="disclosure" data-open={open}>
        <div>
          <div className="px-6 pb-6 grid gap-3 lg:grid-cols-[3fr_2fr]"
            {...(open ? {} : ({ inert: '' } as Record<string, string>))}>
            <div className="surface-well p-4">
              <p className="text-[13px] font-medium text-ink-muted mb-3">
                Matches when {isAnd ? 'all' : 'any'} of these are true
              </p>
              <RuleConditions condition={rule.condition} />
            </div>
            <dl className="surface-well p-4 space-y-3 text-sm">
              <div>
                <dt className="text-[13px] font-medium text-ink-muted">Alert headline</dt>
                <dd className="mt-0.5 font-mono text-[13px] text-ink break-all">{rule.title}</dd>
              </div>
              {rule.body && (
                <div>
                  <dt className="text-[13px] font-medium text-ink-muted">Message</dt>
                  <dd className="mt-0.5 font-mono text-[13px] text-ink break-all whitespace-pre-wrap">{rule.body}</dd>
                </div>
              )}
              <div>
                <dt className="text-[13px] font-medium text-ink-muted">Repeats</dt>
                <dd className="mt-0.5 text-ink">
                  {rule.group_by && rule.group_window_s ? (
                    <>
                      One alert per <code className="font-mono text-[13px]">{rule.group_by}</code> every{' '}
                      {Math.round(rule.group_window_s / 60)} min
                    </>
                  ) : (
                    'Every match raises its own alert'
                  )}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </article>
  );
}
