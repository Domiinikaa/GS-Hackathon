// Formularz dodawania / edycji reguły, z podglądem zwykłym językiem na żywo.
import React, { useState } from 'react';
import { Plus, Trash2, X } from 'lucide-react';
import {
  CHANNELS, COLORS, COLOR_DOT, Channel, Color, Condition, Operator, OPERATORS,
  Rule, SEVERITIES, Severity, groupConditions, groupMode,
} from './ruleTypes';
import { describeRule } from './describeRule';

// W formularzu wartość warunku trzymamy jako tekst (tak jak wpisuje użytkownik)
interface ConditionRow {
  field: string;
  op: Operator;
  value: string;
}

// Tekst z formularza -> właściwa wartość (liczba, lista albo tekst)
function parseValue(op: Operator, raw: string): Condition['value'] {
  const text = raw.trim();
  if (op === 'in') return text.split(',').map((s) => s.trim()).filter(Boolean);
  if (text !== '' && !isNaN(Number(text))) return Number(text);
  return text;
}

// Właściwa wartość -> tekst do pola w formularzu
function valueToText(value: Condition['value']): string {
  return Array.isArray(value) ? value.join(', ') : String(value);
}

interface Props {
  initial?: Rule;               // brak = nowa reguła
  onSave: (rule: Rule) => void;
  onCancel: () => void;
}

const inputClass =
  'w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500';
const labelClass = 'block text-xs font-semibold text-slate-300 mb-1';

export default function RuleForm({ initial, onSave, onCancel }: Props) {
  const [name, setName] = useState(initial?.name ?? '');
  const [team, setTeam] = useState(initial?.team ?? '');
  const [mode, setMode] = useState<'and' | 'or'>(initial ? groupMode(initial.condition) : 'and');
  const [rows, setRows] = useState<ConditionRow[]>(
    initial
      ? groupConditions(initial.condition).map((c) => ({ field: c.field, op: c.op, value: valueToText(c.value) }))
      : [{ field: '', op: 'eq', value: '' }],
  );
  const [channels, setChannels] = useState<Channel[]>(initial?.channels ?? ['ui']);
  const [title, setTitle] = useState(initial?.title ?? '');
  const [body, setBody] = useState(initial?.body ?? '');
  const [severity, setSeverity] = useState<Severity>(initial?.severity ?? 'warning');
  const [color, setColor] = useState<Color>(initial?.color ?? 'amber');
  const [groupBy, setGroupBy] = useState(initial?.group_by ?? '');
  const [groupMinutes, setGroupMinutes] = useState(
    initial?.group_window_s ? String(initial.group_window_s / 60) : '',
  );
  const [error, setError] = useState('');

  // Składa regułę z aktualnego stanu formularza (używane do podglądu i zapisu)
  function buildRule(): Rule {
    const conditions: Condition[] = rows
      .filter((r) => r.field.trim() !== '')
      .map((r) => ({ field: r.field.trim(), op: r.op, value: parseValue(r.op, r.value) }));
    const minutes = Number(groupMinutes);
    return {
      id: initial?.id ?? `rule-${Date.now()}`,
      name: name.trim(),
      team: team.trim(),
      enabled: initial?.enabled ?? true,
      condition: mode === 'and' ? { and: conditions } : { or: conditions },
      channels,
      title: title.trim(),
      body: body.trim() || undefined,
      severity,
      color,
      group_by: groupBy.trim() || undefined,
      group_window_s: groupBy.trim() && minutes > 0 ? minutes * 60 : undefined,
    };
  }

  function updateRow(index: number, change: Partial<ConditionRow>) {
    setRows(rows.map((row, i) => (i === index ? { ...row, ...change } : row)));
  }

  function toggleChannel(ch: Channel) {
    setChannels(channels.includes(ch) ? channels.filter((c) => c !== ch) : [...channels, ch]);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const rule = buildRule();
    if (!rule.name) return setError('Give the rule a name.');
    if (!rule.team) return setError('Choose who gets notified (team or person).');
    if (groupConditions(rule.condition).length === 0) return setError('Add at least one condition.');
    if (rule.channels.length === 0) return setError('Pick at least one channel.');
    if (!rule.title) return setError('Add an alert title.');
    setError('');
    onSave(rule);
  }

  return (
    <form onSubmit={handleSubmit} className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-white">{initial ? 'Edit rule' : 'New rule'}</h2>
        <button type="button" onClick={onCancel} className="text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* 1. Nazwa i odbiorca */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Rule name</label>
          <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Large rejected trades" />
        </div>
        <div>
          <label className={labelClass}>Who gets notified (team or person)</label>
          <input className={inputClass} value={team} onChange={(e) => setTeam(e.target.value)}
            placeholder="e.g. Rates" />
        </div>
      </div>

      {/* 2. Warunki */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className={labelClass}>When an event matches</span>
          <div className="flex text-xs rounded-lg overflow-hidden border border-slate-700">
            <button type="button" onClick={() => setMode('and')}
              className={`px-3 py-1 ${mode === 'and' ? 'bg-amber-500 text-slate-950 font-bold' : 'text-slate-300'}`}>
              ALL conditions (AND)
            </button>
            <button type="button" onClick={() => setMode('or')}
              className={`px-3 py-1 ${mode === 'or' ? 'bg-amber-500 text-slate-950 font-bold' : 'text-slate-300'}`}>
              ANY condition (OR)
            </button>
          </div>
        </div>

        <div className="space-y-2">
          {rows.map((row, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 items-center">
              <input className={`${inputClass} col-span-4 font-mono`} value={row.field}
                onChange={(e) => updateRow(i, { field: e.target.value })}
                placeholder="field, e.g. payload.desk" />
              <select className={`${inputClass} col-span-3`} value={row.op}
                onChange={(e) => updateRow(i, { op: e.target.value as Operator })}>
                {OPERATORS.map((o) => (
                  <option key={o.value} value={o.value}>{o.symbol} {o.label}</option>
                ))}
              </select>
              <input className={`${inputClass} col-span-4 font-mono`} value={row.value}
                onChange={(e) => updateRow(i, { value: e.target.value })}
                placeholder={row.op === 'in' ? 'A, B, C' : 'value'} />
              <button type="button" onClick={() => setRows(rows.filter((_, j) => j !== i))}
                className="col-span-1 text-slate-500 hover:text-red-400 flex justify-center"
                title="Remove condition">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
        <button type="button" onClick={() => setRows([...rows, { field: '', op: 'eq', value: '' }])}
          className="mt-2 text-xs text-amber-400 hover:text-amber-300 flex items-center space-x-1">
          <Plus className="w-3.5 h-3.5" /><span>Add condition</span>
        </button>
      </div>

      {/* 3. Kanały */}
      <div>
        <span className={labelClass}>Send on channels</span>
        <div className="flex flex-wrap gap-2">
          {CHANNELS.map((ch) => (
            <button key={ch.value} type="button" onClick={() => toggleChannel(ch.value)}
              className={`px-3 py-1.5 rounded-lg text-sm border transition ${
                channels.includes(ch.value)
                  ? 'bg-amber-500/20 border-amber-500 text-amber-300'
                  : 'border-slate-700 text-slate-400 hover:border-slate-500'
              }`}>
              {ch.label}
            </button>
          ))}
        </div>
      </div>

      {/* 4. Wygląd alertu */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Alert title (use {'{{field}}'} to insert values)</label>
          <input className={`${inputClass} font-mono`} value={title} onChange={(e) => setTitle(e.target.value)}
            placeholder="Rejected {{payload.currency}} {{payload.notional}}" />
        </div>
        <div>
          <label className={labelClass}>Alert body (optional)</label>
          <input className={`${inputClass} font-mono`} value={body} onChange={(e) => setBody(e.target.value)}
            placeholder="{{error.message}}" />
        </div>
        <div>
          <label className={labelClass}>Severity</label>
          <select className={inputClass} value={severity} onChange={(e) => setSeverity(e.target.value as Severity)}>
            {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <span className={labelClass}>Colour in the UI</span>
          <div className="flex gap-2 pt-1">
            {COLORS.map((c) => (
              <button key={c} type="button" onClick={() => setColor(c)} title={c}
                className={`w-7 h-7 rounded-full ${COLOR_DOT[c]} ${
                  color === c ? 'ring-2 ring-offset-2 ring-offset-slate-900 ring-white' : 'opacity-60'
                }`} />
            ))}
          </div>
        </div>
      </div>

      {/* 5. Grupowanie (opcjonalne) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Group alerts by field (optional)</label>
          <input className={`${inputClass} font-mono`} value={groupBy} onChange={(e) => setGroupBy(e.target.value)}
            placeholder="e.g. instrument" />
        </div>
        <div>
          <label className={labelClass}>Group window (minutes)</label>
          <input type="number" min="1" className={inputClass} value={groupMinutes}
            onChange={(e) => setGroupMinutes(e.target.value)} placeholder="e.g. 5" />
        </div>
      </div>

      {/* Podgląd zwykłym językiem – aktualizuje się na żywo */}
      <div className="bg-slate-950 border border-slate-800 rounded-lg p-4">
        <p className="text-xs font-semibold uppercase text-slate-500 mb-1">In plain words</p>
        <p className="text-sm text-slate-200">{describeRule(buildRule())}</p>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="flex justify-end gap-3">
        <button type="button" onClick={onCancel}
          className="px-4 py-2 rounded-lg text-sm text-slate-300 border border-slate-700 hover:bg-slate-800">
          Cancel
        </button>
        <button type="submit"
          className="px-4 py-2 rounded-lg text-sm font-bold bg-amber-500 hover:bg-amber-400 text-slate-950">
          Save rule
        </button>
      </div>
    </form>
  );
}
