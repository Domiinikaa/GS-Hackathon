// OSOBA 4 – jak idzie krok runbooka w alercie: rodzaj (auto / manual / approve), warunek, status i wynik.
// Do użycia w szczegółach alertu (frontend/src/alerts/AlertDetails.tsx – Osoba 1):
//   <StepIcon step={step} />  <StepRunStatus step={step} />
//   przyciski: Approve gdy canApprove(step), Mark done gdy canMarkDone(step), Retry gdy canRetry(step)
import { CheckCircle2, CircleSlash, Clock, XCircle } from 'lucide-react';
import type { RunbookStep } from '../shared/types';
import { KIND_CLASS, KIND_HINT, KIND_LABEL, actionLabel, stepKind } from './stepKind';

export function stepFinished(step: RunbookStep): boolean {
  return !!step.done || ['succeeded', 'failed', 'skipped'].includes(step.status ?? '');
}

// Approve: krok czeka na zgodę (po kliknięciu aplikacja od razu go wykona albo człowiek go zrobi)
export function canApprove(step: RunbookStep): boolean {
  return step.approval === 'required' && !step.approved_by && !stepFinished(step);
}

// Mark done: krok ręczny (po zgodzie, jeśli jej wymaga) albo nieudany krok aplikacji ("zrobiłem to sam")
export function canMarkDone(step: RunbookStep): boolean {
  if (step.done) return false;
  const kind = stepKind(step);
  if (kind === 'manual') return true;
  if (kind === 'approve_manual') return !!step.approved_by;
  return step.status === 'failed';
}

// Retry: aplikacja próbuje jeszcze raz (runbookApi.retryStep); krok ze zgodą może ponowić tylko lead / admin
export function canRetry(step: RunbookStep): boolean {
  return step.status === 'failed' && !step.done;
}

export function StepIcon({ step }: { step: RunbookStep }) {
  const cls = 'w-4 h-4 mt-0.5 shrink-0';
  if (step.done || step.status === 'succeeded') return <CheckCircle2 className={`${cls} text-ios-green`} />;
  if (step.status === 'failed') return <XCircle className={`${cls} text-ios-red`} />;
  if (step.status === 'skipped') return <CircleSlash className={`${cls} text-ink-muted`} />;
  return <Clock className={`${cls} text-ink-muted`} />;
}

const STATUS_TEXT: Record<string, { label: string; cls: string }> = {
  succeeded: { label: 'done by the app', cls: 'text-ios-green' },
  failed: { label: 'failed – retry or mark done', cls: 'text-ios-red' },
  skipped: { label: 'skipped', cls: 'text-ink-muted' },
  waiting: { label: 'waiting for a person', cls: 'text-slate-300' },
  waiting_approval: { label: 'waiting for approval', cls: 'text-ios-orange' },
};

export default function StepRunStatus({ step }: { step: RunbookStep }) {
  const kind = stepKind(step);
  const status = step.done ? { label: 'done', cls: 'text-ios-green' } : step.status ? STATUS_TEXT[step.status] : undefined;
  return (
    <div className="space-y-1 mt-1">
      <div className="flex flex-wrap items-center gap-2 text-xs">
<span title={KIND_HINT[kind]} className={`text-xs font-medium px-2 py-0.5 rounded-full ${KIND_CLASS[kind]}`}>{KIND_LABEL[kind]}</span>
{step.action && <span className="font-mono text-ink-muted">{actionLabel(step.action)}</span>}
{step.condition && <span className="text-ink-muted">only if: <span className="text-slate-300">{step.condition}</span></span>}
        
        {status && <span className={status.cls}>{status.label}</span>}
        {step.run_no && step.run_no > 1 ? <span className="text-ink-muted">attempt {step.run_no}</span> : null}
      </div>
      {step.result && step.status !== 'waiting_approval' && (
        <p className={`text-xs ${step.status === 'failed' ? 'text-ios-red' : step.status === 'succeeded' ? 'text-ios-green' : 'text-ink-muted'}`}>
          {step.result}
        </p>
      )}
    </div>
  );
}
