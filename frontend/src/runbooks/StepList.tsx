// Lista kroków runbooka (zwykła instrukcja do przeczytania).
// Do użycia też w szczegółach alertu (Osoba 1): <StepList steps={alert.steps} />
import type { RunbookStep } from '../shared/types';

export default function StepList({ steps, empty = 'No steps.' }: { steps: RunbookStep[]; empty?: string }) {
  if (steps.length === 0) return <p className="text-sm text-slate-500 italic">{empty}</p>;
  return (
    <ol className="space-y-2">
      {steps.map((step, i) => (
        <li key={i} className="flex gap-3 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2">
          <span className="text-xs font-mono text-slate-500 mt-0.5 w-5 shrink-0">{i + 1}.</span>
          <p className="flex-1 min-w-0 text-sm text-slate-200 break-words">{step.text}</p>
        </li>
      ))}
    </ol>
  );
}
