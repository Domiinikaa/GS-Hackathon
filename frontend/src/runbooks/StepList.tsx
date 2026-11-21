// Runbook steps as a numbered timeline (steps really are a sequence): text, step kind
// (auto / manual / needs approval), action and condition.
// With `onKindChange` every step gets a picker to change its kind (runbook editor).
// Also usable in alert details: <StepList steps={alert.steps} />
import type { RunbookStep, StepKind } from '../shared/types';
import { KIND_CLASS, KIND_HINT, KIND_LABEL, actionLabel, allowedKinds, stepKind } from './stepKind';

interface Props {
  steps: RunbookStep[];
  empty?: string;
  onKindChange?: (index: number, kind: StepKind) => void;
}

export function KindBadge({ step }: { step: RunbookStep }) {
  const kind = stepKind(step);
  return (
    <span title={KIND_HINT[kind]} className={`text-xs font-medium px-2 py-0.5 rounded-full ${KIND_CLASS[kind]}`}>
      {KIND_LABEL[kind]}
    </span>
  );
}

export default function StepList({ steps, empty = 'No steps.', onKindChange }: Props) {
  if (steps.length === 0) return <p className="text-sm text-ink-muted">{empty}</p>;
  return (
    <ol className="relative">
      {steps.map((step, i) => {
        const kind = stepKind(step);
        const needsApproval = kind === 'approve' || kind === 'approve_manual';
        const last = i === steps.length - 1;
        return (
          <li key={i} className="relative flex gap-3.5 pb-4 last:pb-0">
            {/* guide line joining this step to the next */}
            {!last && <span className="absolute left-[13px] top-7 bottom-0 w-px bg-white/10" aria-hidden="true" />}
            <span
              className={`relative z-[1] w-[27px] h-[27px] shrink-0 rounded-full flex items-center justify-center text-xs font-semibold tabular-nums ${
                needsApproval
                  ? 'bg-ios-orange/15 text-ios-orange ring-1 ring-ios-orange/40'
                  : 'bg-white/[0.07] text-ink ring-1 ring-white/10'
              }`}
            >
              {i + 1}
            </span>
            <div className="flex-1 min-w-0 pt-[3px]">
              <p className="text-sm text-ink leading-relaxed break-words">{step.text}</p>
              <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                {onKindChange ? (
                  <select value={kind} title={KIND_HINT[kind]} aria-label={`Kind of step ${i + 1}`}
                    onChange={(e) => onKindChange(i, e.target.value as StepKind)}
                    className={`text-xs font-medium rounded-full px-2 py-0.5 border-0 focus:outline-none focus:ring-2 focus:ring-ios-blue ${KIND_CLASS[kind]}`}>
                    {allowedKinds(step).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
                  </select>
                ) : (
                  <KindBadge step={step} />
                )}
                {step.action && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-ink-muted">
                    {actionLabel(step.action)}{step.custom && ' (team action)'}
                  </span>
                )}
                {step.condition && (
                  <span className="text-xs text-ink-muted">Only if <span className="text-ink">{step.condition}</span></span>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
