// Rozwinięta część karty alertu: treść, kroki runbooka (Mark done / Approve) i historia – co zrobiono i kto.
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
    <div className="bg-black/25 ios-divided">
      {alert.body && (
        <div className="ios-row">
          <p className="text-[15px] text-white whitespace-pre-line">{alert.body}</p>
        </div>
      )}
      <div className="ios-row justify-between text-[15px]">
        <span className="text-white">First seen</span><span className="text-ink-muted">{clock(alert.first_seen)}</span>
      </div>
      <div className="ios-row justify-between text-[15px]">
        <span className="text-white">Last seen</span><span className="text-ink-muted">{clock(alert.last_seen)}</span>
      </div>
      <div className="ios-row justify-between text-[15px]">
        <span className="text-white">Times it happened</span><span className="text-ink-muted tabular-nums">{alert.count}</span>
      </div>
      <div className="ios-row justify-between text-[15px]">
        <span className="text-white">Rule</span><code className="font-mono text-[13px] text-ink-muted">{alert.rule_id}</code>
      </div>

      {/* Kroki runbooka */}
      <div className="ios-row text-[13px] text-ink-muted pt-5" style={{ minHeight: 36 }}>What to do</div>
      {alert.steps?.length ? (
        alert.steps.map((step, i) => (
          <StepRow key={i} index={i} step={step} disabled={busy || closed}
            onApprove={() => onAction(alert, 'approve', i)}
            onDone={() => onAction(alert, 'done', i)}
            onRetry={() => onAction(alert, 'retry', i)} />
        ))
      ) : (
        <div className="ios-row text-[15px] text-ink-muted">No runbook attached to this alert yet.</div>
      )}

      {/* Historia: kto co zrobił */}
      <div className="ios-row text-[13px] text-ink-muted pt-5" style={{ minHeight: 36 }}>History</div>
      {(alert.history ?? []).map((h, i) => (
        <div key={i} className="ios-row text-[13px]" style={{ minHeight: 40 }}>
          <span className="w-28 shrink-0 text-ink-muted tabular-nums">{clock(h.at)}</span>
          <span className="w-24 shrink-0 text-white truncate">{h.who}</span>
          <span className="text-ink-muted">{h.what}</span>
        </div>
      ))}
    </div>
  );
}

function StepRow({ index, step, disabled, onApprove, onDone, onRetry }: {
  index: number; step: RunbookStep; disabled: boolean; onApprove: () => void; onDone: () => void; onRetry: () => void;
}) {
  // Status kroku (zrobione przez aplikację / nieudane / pominięte / czeka) i tylko pasujące przyciski
  const finished = stepFinished(step);
  const failed = step.status === 'failed' && !step.done;

  return (
    <div className={`ios-row items-start py-3 ${failed ? 'bg-ios-red/[0.06]' : ''}`}>
      <StepIcon step={step} />

      <div className="flex-1 min-w-0">
        <p className={finished && !failed ? 'text-[15px] text-ink-muted' : 'text-[15px] text-white'}>
          {index + 1}. {step.text}
        </p>
        <StepRunStatus step={step} />
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-0.5 text-[13px]">
          {step.approved_by && (
            <span className="flex items-center gap-1 text-ios-blue">
              <ShieldCheck className="w-3.5 h-3.5" />Approved by {step.approved_by}, {clock(step.approved_at)}
            </span>
          )}
          {step.done && <span className="text-ios-green">Done by {step.done_by}, {clock(step.done_at)}</span>}
        </div>
      </div>

      <div className="shrink-0 flex gap-2">
        {canApprove(step) && (
          <button disabled={disabled} onClick={onApprove}
            className="btn-primary text-[13px] h-8 px-3.5 disabled:opacity-40">
            Approve
          </button>
        )}
        {canRetry(step) && (
          <button disabled={disabled} onClick={onRetry} title="Let the app try this step again"
            className="h-8 px-3.5 rounded-full bg-ios-fill text-[13px] font-semibold text-ios-red hover:bg-white/[0.16] transition-colors disabled:opacity-40">
            Retry
          </button>
        )}
        {canMarkDone(step) && (
          <button disabled={disabled} onClick={onDone} title={failed ? 'You fixed it yourself' : 'You did this step'}
            className="h-8 px-3.5 rounded-full bg-ios-fill text-[13px] font-semibold text-ios-blue hover:bg-white/[0.16] transition-colors disabled:opacity-40">
            Mark done
          </button>
        )}
      </div>
    </div>
  );
}
