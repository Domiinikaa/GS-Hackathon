// OSOBA 1 – rozwinięta część karty alertu: treść, kroki runbooka (Mark done / Approve) i historia.
// Wymaganie 2.6: "An alert should tell people what to do next" + "record what was done and by whom".
import { ShieldCheck } from 'lucide-react';
import type { Alert, RunbookStep } from '../shared/types';
import { parseUtc } from './AlertCard';
import type { OnAlertAction } from './AlertCard';
import StepRunStatus, { StepIcon, canApprove, canMarkDone, canRetry, stepFinished } from '../runbooks/StepRunStatus';

// "21:14" (dzisiaj) albo "20 Nov 21:14" – w czasie lokalnym przeglądarki
function clock(iso?: string): string {
  if (!iso) return '';
  const d = parseUtc(iso);
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return d.toDateString() === new Date().toDateString()
    ? time
    : `${d.toLocaleDateString([], { day: 'numeric', month: 'short' })} ${time}`;
}

interface Props {
  alert: Alert;
  onAction: OnAlertAction;
  busy: boolean;
}

export default function AlertDetails({ alert, onAction, busy }: Props) {
  const closed = alert.status === 'resolved';

  return (
    <div className="border-t border-slate-800 pl-5 pr-4 py-4 space-y-5 text-sm">
      {/* Treść + skąd się wziął */}
      <div className="space-y-1">
        {alert.body && <p className="text-slate-300 whitespace-pre-line">{alert.body}</p>}
        <p className="text-xs text-slate-500">
          First seen {clock(alert.first_seen)} · last seen {clock(alert.last_seen)} · ×{alert.count}
          {' · '}rule <code className="text-slate-400">{alert.rule_id}</code>
        </p>
      </div>

      {/* Kroki runbooka */}
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">What to do</h3>
        {alert.steps?.length ? (
          <ol className="space-y-2">
            {alert.steps.map((step, i) => (
              <StepRow key={i} index={i} step={step} disabled={busy || closed}
                onApprove={() => onAction(alert, 'approve', i)}
                onDone={() => onAction(alert, 'done', i)}
                onRetry={() => onAction(alert, 'retry', i)} />
            ))}
          </ol>
        ) : (
          <p className="text-slate-500 text-xs">No runbook attached to this alert yet.</p>
        )}
      </section>

      {/* Historia: kto co zrobił */}
      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">History</h3>
        <ul className="space-y-1 text-xs">
          {(alert.history ?? []).map((h, i) => (
            <li key={i} className="flex gap-3">
              <span className="w-24 shrink-0 font-mono text-slate-500">{clock(h.at)}</span>
              <span className="w-20 shrink-0 text-slate-300 truncate">{h.who}</span>
              <span className="text-slate-400">{h.what}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function StepRow({ index, step, disabled, onApprove, onDone, onRetry }: {
  index: number; step: RunbookStep; disabled: boolean; onApprove: () => void; onDone: () => void; onRetry: () => void;
}) {
  // Osoba 4: status kroku (zrobione przez aplikację / nieudane / pominięte / czeka) i tylko pasujące przyciski
  const finished = stepFinished(step);
  const failed = step.status === 'failed' && !step.done;
  const border = failed ? 'border-red-500/30 bg-red-500/5'
    : finished ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-slate-800 bg-slate-950/40';

  return (
    <li className={`flex items-start gap-3 rounded-lg border px-3 py-2 ${border}`}>
      <StepIcon step={step} />

      <div className="flex-1 min-w-0">
        <p className={finished && !failed ? 'text-slate-400' : 'text-slate-200'}>
          {index + 1}. {step.text}
        </p>
        <StepRunStatus step={step} />
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 text-xs">
          {step.approved_by && (
            <span className="flex items-center gap-1 text-sky-400">
              <ShieldCheck className="w-3.5 h-3.5" />approved by {step.approved_by} · {clock(step.approved_at)}
            </span>
          )}
          {step.done && <span className="text-emerald-400">done by {step.done_by} · {clock(step.done_at)}</span>}
        </div>
      </div>

      <div className="shrink-0 flex gap-2">
        {canApprove(step) && (
          <button disabled={disabled} onClick={onApprove}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 disabled:opacity-50">
            Approve
          </button>
        )}
        {canRetry(step) && (
          <button disabled={disabled} onClick={onRetry} title="Let the app try this step again"
            className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-red-500/50 text-red-300 hover:bg-red-500/10 disabled:opacity-50">
            Retry
          </button>
        )}
        {canMarkDone(step) && (
          <button disabled={disabled} onClick={onDone} title={failed ? 'You fixed it yourself' : 'You did this step'}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 hover:bg-slate-800 disabled:opacity-50">
            Mark done
          </button>
        )}
      </div>
    </li>
  );
}
