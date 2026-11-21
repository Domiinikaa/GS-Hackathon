// One rule in the list: a one-line summary, with conditions and templates behind "Show details".
import { useId } from 'react';
import { BookOpen, ChevronDown, Pencil, Trash2 } from 'lucide-react';
import type { Channel, Rule, Severity } from './ruleTypes';
import RuleConditions, { countConditions } from './RuleConditions';

const CHANNEL_WORD: Record<Channel, string> = {
  email: 'email',
  sms: 'SMS',
  phone: 'phone call',
  ui: 'in-app',
};

const SEVERITY_STYLE: Record<Severity, { dot: string; pill: string; label: string }> = {
  critical: { dot: 'bg-signal-critical', pill: 'bg-signal-critical/15 text-signal-critical', label: 'Critical' },
  warning: { dot: 'bg-signal-warning', pill: 'bg-signal-warning/15 text-signal-warning', label: 'Warning' },
  info: { dot: 'bg-signal-info', pill: 'bg-signal-info/15 text-signal-info', label: 'Info' },
};

// "email, SMS and phone call"
function listWords(words: string[]): string {
  if (words.length <= 1) return words[0] ?? 'no channel';
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

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
  const sev = SEVERITY_STYLE[rule.severity] ?? SEVERITY_STYLE.info;
  const items = 'and' in rule.condition ? rule.condition.and : rule.condition.or;
  const count = countConditions(items);
  const matchWord = 'and' in rule.condition ? 'all' : 'any';

  return (
    <article className={`surface transition-opacity ${rule.enabled ? '' : 'opacity-60'}`}>
      <div className="flex items-start gap-4 p-5">
        <span className={`mt-2 w-2.5 h-2.5 rounded-full shrink-0 ${sev.dot}`} aria-hidden="true" />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-[17px] font-semibold leading-snug text-white">{rule.name}</h3>
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${sev.pill}`}>{sev.label}</span>
            {rule.runbook_id && (
              <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-white/5 text-ink-muted">
                <BookOpen className="w-3 h-3" />
                {runbookName ?? `Runbook #${rule.runbook_id}`}
              </span>
            )}
          </div>
          <p className="mt-1.5 text-[13px] leading-relaxed text-ink-muted">
            Sends to {rule.team} by{' '}
            {listWords(rule.channels.map((c) => CHANNEL_WORD[c] ?? c))}
            {count > 0
              ? ` when ${count === 1 ? 'its condition matches' : `${matchWord} of ${count} conditions match`}.`
              : ' for every event.'}
          </p>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            role="switch"
            aria-checked={rule.enabled}
            aria-label={rule.enabled ? `Disable ${rule.name}` : `Enable ${rule.name}`}
            title={rule.enabled ? 'Enabled' : 'Disabled'}
            onClick={onToggleEnabled}
            className="switch mr-2"
          />
          <button type="button" onClick={onEdit} title="Edit rule" aria-label={`Edit ${rule.name}`}
            className="w-9 h-9 rounded-full flex items-center justify-center text-ink-muted hover:text-ink hover:bg-white/5">
            <Pencil className="w-4 h-4" />
          </button>
          <button type="button" onClick={onDelete} title="Delete rule" aria-label={`Delete ${rule.name}`}
            className="w-9 h-9 rounded-full flex items-center justify-center text-ink-muted hover:text-signal-critical hover:bg-signal-critical/10">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      <button
        type="button"
        onClick={onToggleOpen}
        aria-expanded={open}
        aria-controls={detailsId}
        className="w-full flex items-center justify-between px-5 py-2.5 border-t border-white/[0.06] text-[13px] font-medium text-ink-muted hover:text-ink hover:bg-white/[0.03] rounded-b-[20px]"
      >
        {open ? 'Hide details' : 'Show details'}
        <ChevronDown className={`w-4 h-4 transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
      </button>

      <div id={detailsId} className="disclosure" data-open={open}>
        <div>
          <div className="px-5 pb-5 grid gap-3 md:grid-cols-[3fr_2fr]"
            {...(open ? {} : ({ inert: '' } as Record<string, string>))}>
            <div className="surface-well p-4">
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
