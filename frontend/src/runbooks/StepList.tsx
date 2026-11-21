// Lista kroków runbooka (zwykła instrukcja do przeczytania).
// Do użycia też w szczegółach alertu (Osoba 1): <StepList steps={alert.steps} />
import { ShieldAlert } from 'lucide-react';
import type { RunbookStep } from '../shared/types';

export default function StepList({ steps, empty = 'No steps.' }: { steps: RunbookStep[]; empty?: string }) {
  if (steps.length === 0) return <p className="text-sm text-slate-500 italic">{empty}</p>;
  return (
    <ol className="space-y-2">
      {steps.map((step, i) => (
        <li key={i} className="flex gap-3 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2">
          <span className="text-xs font-mono text-slate-500 mt-0.5 w-5 shrink-0">{i + 1}.</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-slate-200 break-words">{step.text}</p>
            {(step.action || step.approval === 'required') && (
              <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 text-xs">
                {step.action && (
                  <span className="font-mono text-slate-400">action: {step.action}</span>
                )}
                {step.approval === 'required' && (
                  <span className="inline-flex items-center gap-1 text-amber-400">
                    <ShieldAlert className="w-3.5 h-3.5" />
                    needs approval
                  </span>
                )}
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
