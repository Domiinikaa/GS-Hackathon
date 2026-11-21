// Add / edit rule form.
import React, { useEffect, useState } from 'react';
import { Users, X } from 'lucide-react';
import {
  CHANNELS, COLOR_DOT, Channel, Condition, Operator,
  Rule, SEVERITY_OPTIONS, Severity, colorForSeverity, groupItems, groupMode, isFlat, isLeaf,
} from './ruleTypes';
import { FieldHint, PlannedRecipient, errorMessage, rulesApi } from './rulesApi';
import RuleConditions from './RuleConditions';
import ConditionEditor, { ConditionRow, EMPTY_ROW } from './ConditionEditor';

// Form text -> real value (number, list or text)
function parseValue(op: Operator, raw: string): Condition['value'] {
  const text = raw.trim();
  if (op === 'in') return text.split(',').map((s) => s.trim()).filter(Boolean);
  if (text !== '' && !isNaN(Number(text))) return Number(text);
  return text;
}

// Real value -> text for the form field
function valueToText(value: Condition['value']): string {
  return Array.isArray(value) ? value.join(', ') : String(value);
}

interface Props {
  initial?: Rule;               // missing = new rule
  onSave: (rule: Rule) => Promise<string | null>; // returns an error message or null
  onCancel: () => void;
}

const inputClass =
  'w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500';
const labelClass = 'block text-xs font-semibold text-slate-300 mb-1';
const hintClass = 'text-xs text-slate-500 mt-1';

export default function RuleForm({ initial, onSave, onCancel }: Props) {
  const [name, setName] = useState(initial?.name ?? '');
  const [team, setTeam] = useState(initial?.team ?? '');
  const [mode, setMode] = useState<'and' | 'or'>(initial ? groupMode(initial.condition) : 'and');
  const [rows, setRows] = useState<ConditionRow[]>(
    initial
      ? groupItems(initial.condition).filter(isLeaf).map((c) => ({ field: c.field, op: c.op, value: valueToText(c.value) }))
      : [{ ...EMPTY_ROW }],
  );
  const [channels, setChannels] = useState<Channel[]>(initial?.channels ?? ['ui']);
  const [title, setTitle] = useState(initial?.title ?? '');
  const [body, setBody] = useState(initial?.body ?? '');
  const [severity, setSeverity] = useState<Severity>(initial?.severity ?? 'warning');
  const [groupBy, setGroupBy] = useState(initial?.group_by ?? '');
  const [groupMinutes, setGroupMinutes] = useState(
    initial?.group_window_s ? String(initial.group_window_s / 60) : '',
  );
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  // Rules with nested groups (created via the API) keep their conditions unchanged in this form
  const nested = initial ? !isFlat(initial.condition) : false;
  const [targets, setTargets] = useState<{ teams: string[]; people: string[] }>({ teams: [], people: [] });
  const [fieldHints, setFieldHints] = useState<FieldHint[]>([]);
  const [recipients, setRecipients] = useState<PlannedRecipient[] | null>(null);

  // Suggestions: teams/people and field names from real events
  useEffect(() => {
    rulesApi.teams().then(setTargets).catch(() => {});
    rulesApi.fields().then(setFieldHints).catch(() => {});
  }, []);

  // "Who will be notified" preview, refreshed half a second after the last change
  useEffect(() => {
    const target = team.trim();
    if (!target || channels.length === 0) {
      setRecipients(null);
      return;
    }
    const timer = window.setTimeout(() => {
      rulesApi.previewRecipients(target, severity, channels).then(setRecipients).catch(() => setRecipients(null));
    }, 500);
    return () => window.clearTimeout(timer);
  }, [team, severity, channels]);

  // Builds the rule from the current form state
  function buildRule(): Rule {
    const conditions: Condition[] = rows
      .filter((r) => r.field.trim() !== '')
      .map((r) => ({ field: r.field.trim(), op: r.op, value: parseValue(r.op, r.value) }));
    const minutes = Number(groupMinutes);
    return {
      id: initial?.id ?? '', // new rule: the backend derives the id from the name
      name: name.trim(),
      team: team.trim(),
      enabled: initial?.enabled ?? true,
      condition: nested && initial ? initial.condition : mode === 'and' ? { and: conditions } : { or: conditions },
      channels,
      title: title.trim(),
      body: body.trim() || undefined,
      severity,
      color: colorForSeverity(severity), // the colour always follows the urgency
      group_by: groupBy.trim() || undefined,
      group_window_s: groupBy.trim() && minutes > 0 ? minutes * 60 : undefined,
    };
  }

  function toggleChannel(ch: Channel) {
    setChannels(channels.includes(ch) ? channels.filter((c) => c !== ch) : [...channels, ch]);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const rule = buildRule();
    if (!rule.name) return setError('Give the rule a name.');
    if (!rule.team) return setError('Choose who receives the alerts (team or person).');
    if (groupItems(rule.condition).length === 0) return setError('Add at least one condition.');
    if (rule.channels.length === 0) return setError('Pick at least one way to notify.');
    if (!rule.title) return setError('Add an alert headline.');
    setError('');
    setSaving(true);
    try {
      const failure = await onSave(rule);
      if (failure) setError(failure);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-white">{initial ? 'Edit rule' : 'New rule'}</h2>
        <button type="button" onClick={onCancel} className="text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* 1. Name and recipient */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Rule name</label>
          <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Large rejected trades" />
                  </div>
        <div>
          <label className={labelClass}>Send alerts to</label>
          <select className={inputClass} value={team} onChange={(e) => setTeam(e.target.value)}>
            <option value="">Choose a team or person…</option>
            {team && !targets.teams.includes(team) && !targets.people.includes(team) && (
              <option value={team}>{team} (not found)</option>
            )}
            <optgroup label="Teams (Admin & Invites)">
              {targets.teams.map((t) => <option key={`t-${t}`} value={t}>{t}</option>)}
            </optgroup>
            <optgroup label="One person">
              {targets.people.map((p) => <option key={`p-${p}`} value={p}>{p}</option>)}
            </optgroup>
          </select>
          <p className={hintClass}>Team or person</p>
        </div>
      </div>

      {/* 2. Conditions */}
      {nested && initial ? (
        <div>
          <span className={labelClass}>Raise an alert when an incoming event matches</span>
          <div className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2">
            <RuleConditions condition={initial.condition} />
          </div>
          <p className={hintClass}>Nested conditions – kept as they are; change them via the API</p>
        </div>
      ) : (
        <ConditionEditor mode={mode} onModeChange={setMode} rows={rows} onRowsChange={setRows} fieldHints={fieldHints} />
      )}

      {/* 3. Urgency (also sets the alert colour) */}
      <div>
        <span className={labelClass}>How urgent is it?</span>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {SEVERITY_OPTIONS.map((o) => (
            <button key={o.value} type="button" onClick={() => setSeverity(o.value)}
              aria-pressed={severity === o.value}
              className={`text-left rounded-lg border px-3 py-2 transition ${
                severity === o.value ? 'border-white bg-slate-800' : 'border-slate-700 hover:border-slate-500 opacity-70'
              }`}>
              <span className="flex items-center gap-2 text-sm font-bold text-white">
                <span className={`w-3 h-3 rounded-full ${COLOR_DOT[o.color]}`} />{o.label}
              </span>
              <span className="block text-xs text-slate-400 mt-0.5">{o.hint}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 4. Channels */}
      <div>
        <span className={labelClass}>Notify via</span>
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
        <p className={hintClass}>UI = live feed in this app</p>
      </div>

      {/* 5. Alert text */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Alert headline</label>
          <input className={`${inputClass} font-mono`} value={title} onChange={(e) => setTitle(e.target.value)}
            placeholder="Rejected {{payload.currency}} {{payload.notional}}" />
          <p className={hintClass}>{'{{field}}'} inserts a value from the event</p>
        </div>
        <div>
          <label className={labelClass}>Alert details (optional)</label>
          <input className={`${inputClass} font-mono`} value={body} onChange={(e) => setBody(e.target.value)}
            placeholder="{{error.message}}" />
                  </div>
      </div>

      {/* 6. Combining repeated alerts (optional) */}
      <div>
        <span className={labelClass}>Combine repeated alerts (optional)</span>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Same problem if this field is equal</label>
            <input className={`${inputClass} font-mono`} value={groupBy} onChange={(e) => setGroupBy(e.target.value)}
              placeholder="e.g. instrument" />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Time window (minutes)</label>
            <input type="number" min="1" className={inputClass} value={groupMinutes}
              onChange={(e) => setGroupMinutes(e.target.value)} placeholder="e.g. 5" />
          </div>
        </div>
        <p className={hintClass}>One alert with a counter instead of many</p>
      </div>

      {/* Who gets alerts from this rule, computed by the backend from people's preferences */}
      {recipients && (
        <div className="bg-slate-950 border border-slate-800 rounded-lg p-4">
          <p className="text-xs font-semibold uppercase text-slate-500 mb-2 flex items-center gap-1">
            <Users className="w-3.5 h-3.5" /> Who will be notified (right now)
          </p>
          {recipients.length === 0 ? (
            <p className="text-sm text-amber-300">Nobody – no people in “{team.trim()}”. Add them on the People page.</p>
          ) : (
            <ul className="space-y-1">
              {recipients.map((r, i) => (
                <li key={i} className="text-sm text-slate-200">
                  <span className="font-semibold">{r.name.startsWith('team:') ? `Team feed (${r.name.slice(5)})` : r.name}</span>
                  {' → '}
                  <span className="text-amber-300">{CHANNELS.find((c) => c.value === r.channel)?.label ?? r.channel}</span>
                  {r.to && <span className="text-slate-500 font-mono"> {r.to}</span>}
                  <span className="block text-xs text-slate-500">{r.reason}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="flex justify-end gap-3">
        <button type="button" onClick={onCancel}
          className="px-4 py-2 rounded-lg text-sm text-slate-300 border border-slate-700 hover:bg-slate-800">
          Cancel
        </button>
        <button type="submit" disabled={saving}
          className="px-4 py-2 rounded-lg text-sm font-bold bg-amber-500 hover:bg-amber-400 text-slate-950 disabled:opacity-60">
          {saving ? 'Saving…' : 'Save rule'}
        </button>
      </div>
    </form>
  );
}
