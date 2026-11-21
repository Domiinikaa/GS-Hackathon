// OSOBA 4 – rodzaj kroku runbooka (to samo co services/runbook_parser.step_kind po stronie backendu).
import type { RunbookStep, StepKind } from '../shared/types';

export type { StepKind };

export const KNOWN_ACTIONS = ['http_get', 'retry_workflow', 'restart_service', 'webhook', 'open_ticket', 'escalate', 'wait'];

export const ALL_KINDS: StepKind[] = ['auto', 'approve', 'manual', 'approve_manual'];

export function hasKnownAction(step: RunbookStep): boolean {
  return !!step.action && KNOWN_ACTIONS.includes(step.action);
}

export function stepKind(step: RunbookStep): StepKind {
  const known = hasKnownAction(step);
  if (step.kind && (known || step.kind === 'manual' || step.kind === 'approve_manual')) return step.kind;
  if (known) return step.approval === 'required' ? 'approve' : 'auto';
  return step.approval === 'required' ? 'approve_manual' : 'manual';
}

// Rodzaje, które mają sens dla kroku: "auto" / "approve" tylko, gdy aplikacja umie wykonać akcję
export function allowedKinds(step: RunbookStep): StepKind[] {
  return hasKnownAction(step) ? ALL_KINDS : ['manual', 'approve_manual'];
}

// Ręczny wybór rodzaju (jak services/runbook_parser.set_kind): ustawia też zgodne pole approval
export function withKind(step: RunbookStep, kind: StepKind): RunbookStep {
  return { ...step, kind, approval: kind === 'approve' || kind === 'approve_manual' ? 'required' : 'none' };
}

export const KIND_LABEL: Record<StepKind, string> = {
  manual: 'manual',
  auto: 'auto',
  approve: 'needs approval',
  approve_manual: 'approval, then manual',
};

export const KIND_HINT: Record<StepKind, string> = {
  manual: 'A person does this and marks it done',
  auto: 'The app does this by itself',
  approve: 'The app does this after a team lead approves it',
  approve_manual: 'A team lead approves it, then a person does it and marks it done',
};

export const KIND_CLASS: Record<StepKind, string> = {
  manual: 'border-slate-600 text-slate-300',
  auto: 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10',
  approve: 'border-amber-500/40 text-amber-300 bg-amber-500/10',
  approve_manual: 'border-amber-500/40 text-amber-300 bg-amber-500/10',
};

export const ACTION_LABEL: Record<string, string> = {
  http_get: 'HTTP check',
  retry_workflow: 'Retry workflow',
  restart_service: 'Restart service',
  webhook: 'Webhook',
  open_ticket: 'Open ticket',
  escalate: 'Escalate',
  wait: 'Wait',
};
