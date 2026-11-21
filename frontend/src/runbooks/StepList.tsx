// Runbook steps as a numbered timeline (steps really are a sequence).
// Also usable in alert details: <StepList steps={alert.steps} />
import type { RunbookStep } from '../shared/types';

export default function StepList({ steps, empty = 'No steps.' }: { steps: RunbookStep[]; empty?: string }) {
  if (steps.length === 0) return <p className="text-sm text-ink-muted">{empty}</p>;
  return (
    <ol className="relative">
      {steps.map((step, i) => {
        const last = i === steps.length - 1;
        return (
          <li key={i} className="relative flex gap-3.5 pb-4 last:pb-0">
            {/* guide line joining this step to the next */}
            {!last && <span className="absolute left-[13px] top-7 bottom-0 w-px bg-white/10" aria-hidden="true" />}
            <span
              className={`relative z-[1] w-[27px] h-[27px] shrink-0 rounded-full flex items-center justify-center text-xs font-semibold tabular-nums ${
                step.approval === 'required'
                  ? 'bg-signal-warning/15 text-signal-warning ring-1 ring-signal-warning/40'
                  : 'bg-white/[0.07] text-ink ring-1 ring-white/10'
              }`}
            >
              {i + 1}
            </span>
            <div className="flex-1 min-w-0 pt-[3px]">
              <p className="text-sm text-ink leading-relaxed break-words">{step.text}</p>
              {(step.action || step.approval === 'required') && (
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {step.approval === 'required' && (
                    <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-signal-warning/15 text-signal-warning">
                      Needs approval
                    </span>
                  )}
                  {step.action && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-ink-muted">
                      Runs <code className="font-mono text-[11px] text-ink">{step.action}</code>
                    </span>
                  )}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
