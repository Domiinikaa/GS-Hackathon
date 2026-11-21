// Condition rows that read like a sentence: "When <field> <is greater than> <value>  AND ...".
import React, { useState } from 'react';
import { Plus, Trash2, X } from 'lucide-react';
import { FieldKind, Operator, operatorsFor } from './ruleTypes';
import type { FieldHint } from './rulesApi';

// A condition as typed in the form (the value stays text until the rule is saved)
export interface ConditionRow {
  field: string;
  op: Operator;
  value: string;
}

export const EMPTY_ROW: ConditionRow = { field: '', op: 'eq', value: '' };

interface Props {
  mode: 'and' | 'or';
  onModeChange: (mode: 'and' | 'or') => void;
  rows: ConditionRow[];
  onRowsChange: (rows: ConditionRow[]) => void;
  fieldHints: FieldHint[];
}

const inputClass =
  'field w-full px-3 py-2 text-sm';

function kindOf(hint: FieldHint | undefined): FieldKind | null {
  if (!hint) return null;
  return hint.type === 'number' ? 'number' : 'text';
}

function exampleText(hint: FieldHint): string {
  const label = hint.type === 'number' ? 'number' : hint.type === 'string' ? 'text' : hint.type;
  return `${label} · e.g. ${JSON.stringify(hint.example)}`.slice(0, 70);
}

// "is one of" values shown as removable chips; stored as "A, B, C"
function ChipsInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  const [draft, setDraft] = useState('');
  const chips = value.split(',').map((s) => s.trim()).filter(Boolean);

  function add(text: string) {
    const parts = text.split(',').map((s) => s.trim()).filter(Boolean);
    if (parts.length) onChange([...chips, ...parts.filter((p) => !chips.includes(p))].join(', '));
    setDraft('');
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      add(draft);
    } else if (e.key === 'Backspace' && !draft && chips.length) {
      onChange(chips.slice(0, -1).join(', '));
    }
  }

  return (
    <div className={`${inputClass} flex flex-wrap items-center gap-1 py-1.5`}>
      {chips.map((chip) => (
        <span key={chip} className="flex items-center gap-1 bg-white/[0.06] border border-white/10 rounded px-2 py-0.5 text-xs font-mono">
          {chip}
          <button type="button" aria-label={`Remove ${chip}`} onClick={() => onChange(chips.filter((c) => c !== chip).join(', '))}
            className="text-ink-muted hover:text-white">
            <X className="w-3 h-3" />
          </button>
        </span>
      ))}
      <input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKeyDown} onBlur={() => add(draft)}
        placeholder={chips.length ? '' : placeholder} aria-label="Add value"
        className="flex-1 min-w-[6rem] bg-transparent outline-none font-mono text-sm" />
    </div>
  );
}

export default function ConditionEditor({ mode, onModeChange, rows, onRowsChange, fieldHints }: Props) {
  const hintFor = (field: string) => fieldHints.find((h) => h.path === field.trim());

  function update(index: number, change: Partial<ConditionRow>) {
    onRowsChange(rows.map((row, i) => {
      if (i !== index) return row;
      const next = { ...row, ...change };
      // When the field changes, keep the operator only if it still fits the field type
      if (change.field !== undefined) {
        const allowed = operatorsFor(kindOf(hintFor(next.field)));
        if (!allowed.some((o) => o.value === next.op)) next.op = allowed[0].value;
      }
      return next;
    }));
  }

  return (
    <div>
      <span className="block text-xs font-semibold text-slate-300 mb-2">Raise an alert when an incoming event matches</span>

      <div className="space-y-3">
        {rows.map((row, i) => {
          const hint = hintFor(row.field);
          const ops = operatorsFor(kindOf(hint));
          // keep an operator from an older rule visible even if it doesn't fit the detected type
          const opList = ops.some((o) => o.value === row.op) ? ops : [...ops, ...operatorsFor(null).filter((o) => o.value === row.op)];
          const placeholder = hint ? String(hint.example ?? '') : row.op === 'in' ? 'type a value, press Enter' : 'value';
          return (
            <div key={i} className="grid grid-cols-12 gap-2 items-start">
              {/* "When" for the first row, clickable AND / OR for the next ones */}
              <div className="col-span-1 pt-2 text-xs font-semibold">
                {i === 0 ? (
                  <span className="text-ink-muted">When</span>
                ) : (
                  <button type="button" onClick={() => onModeChange(mode === 'and' ? 'or' : 'and')}
                    title="Click to switch between AND and OR"
                    className="px-2 py-0.5 rounded border border-amber-500/60 text-amber-300 hover:bg-amber-500/10">
                    {mode.toUpperCase()}
                  </button>
                )}
              </div>

              <div className="col-span-4">
                <input className={`${inputClass} field font-mono`} value={row.field} list="rule-fields"
                  onChange={(e) => update(i, { field: e.target.value })}
                  placeholder="choose a field" aria-label="Event field" />
                <p className="text-xs text-slate-500 mt-1 h-4 truncate">{hint ? exampleText(hint) : ''}</p>
              </div>

              <select className={`${inputClass} field col-span-3`} value={row.op} aria-label="Operator"
                onChange={(e) => update(i, { op: e.target.value as Operator })}>
                {opList.map((o) => <option key={o.value} value={o.value}>{o.phrase}</option>)}
              </select>

              <div className="col-span-3">
                {row.op === 'in' ? (
                  <ChipsInput value={row.value} onChange={(v) => update(i, { value: v })} placeholder={placeholder} />
                ) : (
                  <input className={`${inputClass} field font-mono`} value={row.value} aria-label="Value"
                    inputMode={kindOf(hint) === 'number' ? 'decimal' : undefined}
                    onChange={(e) => update(i, { value: e.target.value })}
                    placeholder={row.op === 'wildcard' ? 'e.g. pricing-engine-*' : placeholder} />
                )}
              </div>

              <button type="button" onClick={() => onRowsChange(rows.filter((_, j) => j !== i))}
                disabled={rows.length === 1}
                className="col-span-1 pt-2 text-slate-500 hover:text-red-400 disabled:opacity-30 flex justify-center"
                title="Remove condition">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>

      <datalist id="rule-fields">
        {fieldHints.map((h) => <option key={h.path} value={h.path}>{exampleText(h)}</option>)}
      </datalist>

      <button type="button" onClick={() => onRowsChange([...rows, { ...EMPTY_ROW }])}
        className="mt-2 text-xs text-amber-400 hover:text-amber-300 flex items-center space-x-1">
        <Plus className="w-3.5 h-3.5" /><span>Add condition</span>
      </button>
    </div>
  );
}
