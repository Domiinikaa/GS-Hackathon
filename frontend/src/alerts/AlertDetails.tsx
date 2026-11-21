// OSOBA 1 – rozwinięta część karty alertu: treść, kroki runbooka (Mark done / Approve) i historia.
// Wymaganie 2.6: "An alert should tell people what to do next" + "record what was done and by whom".
import { CheckCircle2, Circle, ShieldAlert, ShieldCheck } from 'lucide-react';
import type { Alert, RunbookStep } from '../shared/types';
import { parseUtc } from './AlertCard';
import type { OnAlertAction } from './AlertCard';

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
    <div className="border-t border-white/[0.06] px-6 py-5 space-y-6 text-sm">
      {/* Treść + skąd się wziął */}
      <div className="space-y-1">
        {alert.body && <p className="text-slate-300 whitespace-pre-line">{alert.body}</p>}
        <p className="text-xs text-slate-500">
          First seen {clock(alert.first_seen)} · last seen {clock(alert.last_seen)} · ×{alert.count}
          {' · '}rule <code className="text-ink-muted">{alert.rule_id}</code>
        </p>
      </div>

      {/* Kroki runbooka */}
      <section>
        <h3 className="text-[13px] font-medium text-ink-muted mb-2.5">What to do</h3>
        {alert.steps?.length ? (
          <ol className="space-y-2">
            {alert.steps.map((step, i) => (
              <StepRow key={i} index={i} step={step} disabled={busy || closed}
                onApprove={() => onAction(alert, 'approve', i)}
                onDone={() => onAction(alert, 'done', i)} />
            ))}
          </ol>
        ) : (
          <p className="text-slate-500 text-xs">No runbook attached to this alert yet.</p>
        )}
      </section>

      {/* Historia: kto co zrobił */}
      <section>
        <h3 className="text-[13px] font-medium text-ink-muted mb-2.5">History</h3>
        <ul className="space-y-1 text-xs">
          {(alert.history ?? []).map((h, i) => (
            <li key={i} className="flex gap-3">
              <span className="w-24 shrink-0 font-mono text-slate-500">{clock(h.at)}</span>
              <span className="w-20 shrink-0 text-slate-300 truncate">{h.who}</span>
              <span className="text-ink-muted">{h.what}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function StepRow({ index, step, disabled, onApprove, onDone }: {
  index: number; step: RunbookStep; disabled: boolean; onApprove: () => void; onDone: () => void;
}) {
  const risky = step.approval === 'required';
  const waitingForApproval = risky && !step.approved_by;

  return (
    <li className={`flex items-start gap-3 rounded-lg border px-3 py-2 ${
      step.done ? 'border-emerald-500/20 bg-emerald-500/5' : 'surface-well'}`}>
      {step.done
        ? <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-emerald-400" />
        : <Circle className="w-4 h-4 mt-0.5 shrink-0 text-slate-600" />}

      <div className="flex-1 min-w-0">
        <p className={step.done ? 'text-ink-muted line-through decoration-slate-600' : 'text-slate-200'}>
          {index + 1}. {step.text}
        </p>
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 text-xs">
          {step.action && <span className="font-mono text-slate-500">action: {step.action}</span>}
          {waitingForApproval && (
            <span className="flex items-center gap-1 text-amber-400"><ShieldAlert className="w-3.5 h-3.5" />needs approval</span>
          )}
          {step.approved_by && (
            <span className="flex items-center gap-1 text-sky-400">
              <ShieldCheck className="w-3.5 h-3.5" />approved by {step.approved_by} · {clock(step.approved_at)}
            </span>
          )}
          {step.done && <span className="text-emerald-400">done by {step.done_by} · {clock(step.done_at)}</span>}
        </div>
      </div>

      {!step.done && (
        <div className="shrink-0 flex gap-2">
          {waitingForApproval ? (
            <button disabled={disabled} onClick={onApprove}
              className="btn-primary text-xs px-3 py-1.5 disabled:opacity-50">
              Approve
            </button>
          ) : (
            <button disabled={disabled} onClick={onDone}
              className="glass-pill text-xs font-semibold px-3.5 py-1.5 text-slate-200 hover:bg-white/10 transition-colors disabled:opacity-50">
              Mark done
            </button>
          )}
        </div>
      )}
    </li>
  );
}
