// Lista kroków runbooka: tekst, rodzaj kroku (auto / manual / needs approval), akcja i warunek.
// Z `onKindChange` przy każdym kroku jest lista do zmiany rodzaju (edytor runbooka).
// Do użycia też w szczegółach alertu (Osoba 1): <StepList steps={alert.steps} />
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
    <span title={KIND_HINT[kind]} className={`px-1.5 py-0.5 rounded border ${KIND_CLASS[kind]}`}>
      {KIND_LABEL[kind]}
    </span>
  );
}

export default function StepList({ steps, empty = 'No steps.', onKindChange }: Props) {
  if (steps.length === 0) return <p className="text-sm text-slate-500 italic">{empty}</p>;
  return (
    <ol className="space-y-2">
      {steps.map((step, i) => {
        const kind = stepKind(step);
        return (
          <li key={i} className="flex gap-3 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2">
            <span className="text-xs font-mono text-slate-500 mt-0.5 w-5 shrink-0">{i + 1}.</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-200 break-words">{step.text}</p>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-xs">
                {onKindChange ? (
                  <select value={kind} title={KIND_HINT[kind]} aria-label={`Kind of step ${i + 1}`}
                    onChange={(e) => onKindChange(i, e.target.value as StepKind)}
                    className={`rounded border px-1.5 py-0.5 bg-slate-950 focus:outline-none ${KIND_CLASS[kind]}`}>
                    {allowedKinds(step).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
                  </select>
                ) : (
                  <KindBadge step={step} />
                )}
                {step.action && (
                  <span className="font-mono text-slate-400">{actionLabel(step.action)}{step.custom && ' (team action)'}</span>
                )}
                {step.condition && (
                  <span className="text-slate-500">only if: <span className="text-slate-300">{step.condition}</span></span>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
