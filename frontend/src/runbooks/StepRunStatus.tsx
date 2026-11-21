// OSOBA 4 – jak idzie krok runbooka w alercie: rodzaj (auto / manual / approve), warunek, status i wynik.
// Używane w szczegółach alertu (frontend/src/alerts/AlertDetails.tsx).
import { Ban, CheckCircle2, CircleSlash, Clock, Loader2, OctagonX, XCircle } from 'lucide-react';
import type { RunbookStep } from '../shared/types';
import { ACTION_LABEL, KIND_CLASS, KIND_HINT, KIND_LABEL, stepKind } from './stepKind';

export function stepFinished(step: RunbookStep): boolean {
  return !!step.done || ['succeeded', 'failed', 'skipped', 'cancelled'].includes(step.status ?? '');
}

// Krok zatrzymał procedurę: człowiek wybiera Retry (runbookApi.retryStep), Mark done albo Abort (abortRunbook)
export function stepStopped(step: RunbookStep): boolean {
  return step.status === 'error' && !step.done;
}

// Pierwszy niezakończony krok – tam jest teraz procedura
export function currentStepIndex(steps: RunbookStep[]): number {
  return steps.findIndex((s) => !stepFinished(s));
}

// Czy "Approve up to here" (runbookApi.approveUntil) ma sens dla kroku `index`:
// od obecnego kroku do tego nie ma kroku manual ani błędu, a po drodze jest coś do zatwierdzenia
export function canApproveUntil(steps: RunbookStep[], index: number): boolean {
  const cur = currentStepIndex(steps);
  if (cur < 0 || index < cur) return false;
  let pending = 0;
  for (let j = cur; j <= index; j++) {
    const s = steps[j];
    if (stepFinished(s)) continue;
    if (s.status === 'error') return false;
    const kind = stepKind(s);
    if (kind === 'manual') return false;
    if (kind === 'approve_manual' && j < index) return false;
    if (s.approval === 'required' && !s.approved_by) pending++;
  }
  return pending > 1;          // przy jednym kroku wystarczy zwykły Approve
}

// Czy człowiek może kliknąć "Mark done": kroki ręczne, oraz nieudany krok aplikacji (człowiek załatwił to sam)
export function canMarkDone(step: RunbookStep): boolean {
  if (step.done) return false;
  const kind = stepKind(step);
  if (kind === 'manual') return true;
  if (kind === 'approve_manual') return !!step.approved_by;
  return step.status === 'failed';
}

export function StepIcon({ step }: { step: RunbookStep }) {
  const cls = 'w-4 h-4 mt-0.5 shrink-0';
  if (step.done || step.status === 'succeeded') return <CheckCircle2 className={`${cls} text-ios-green`} />;
  if (step.status === 'failed') return <XCircle className={`${cls} text-rose-300`} />;
  if (step.status === 'error') return <OctagonX className={`${cls} text-red-500`} />;
  if (step.status === 'cancelled') return <Ban className={`${cls} text-slate-500`} />;
  if (step.status === 'skipped') return <CircleSlash className={`${cls} text-slate-500`} />;
  if (step.status === 'running' || step.status === 'queued') return <Loader2 className={`${cls} text-sky-400 animate-spin`} />;
  return <Clock className={`${cls} text-slate-500`} />;
}

const STATUS_TEXT: Record<string, { label: string; cls: string }> = {
  queued: { label: 'queued', cls: 'text-sky-300' },
  running: { label: 'running…', cls: 'text-sky-300' },
  succeeded: { label: 'done by the app', cls: 'text-ios-green' },
  failed: { label: 'failed – the runbook goes on', cls: 'text-rose-300' },
  error: { label: 'stopped the runbook – retry, mark done or abort', cls: 'text-rose-300 font-semibold' },
  cancelled: { label: 'cancelled', cls: 'text-slate-500' },
  skipped: { label: 'skipped', cls: 'text-ink-muted' },
  waiting: { label: 'waiting for a person', cls: 'text-slate-300' },
  waiting_approval: { label: 'waiting for approval', cls: 'text-ios-orange' },
};

export default function StepRunStatus({ step }: { step: RunbookStep }) {
  const kind = stepKind(step);
  const status = step.status ? STATUS_TEXT[step.status] : undefined;
  return (
    <div className="space-y-1 mt-1">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span title={KIND_HINT[kind]} className={`text-xs font-medium px-2 py-0.5 rounded-full ${KIND_CLASS[kind]}`}>{KIND_LABEL[kind]}</span>
        {step.action && <span className="font-mono text-slate-500">{ACTION_LABEL[step.action] ?? step.action}</span>}
        {step.condition && <span className="text-slate-500">only if: <span className="text-slate-300">{step.condition}</span></span>}
        {status && <span className={status.cls}>{status.label}</span>}
        {step.run_no && step.run_no > 1 ? <span className="text-slate-500">attempt {step.run_no}</span> : null}
      </div>
      {step.result && step.status !== 'waiting_approval' && (
        <p className={`text-xs ${step.status === 'failed' || step.status === 'error' ? 'text-rose-200' : step.status === 'succeeded' ? 'text-ios-green' : 'text-ink-muted'}`}>
          {step.result}
        </p>
      )}
    </div>
  );
}
