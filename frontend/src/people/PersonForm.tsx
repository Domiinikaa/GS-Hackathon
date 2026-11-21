// Add / edit person form.
import React, { useState } from 'react';
import { X } from 'lucide-react';
import { CHANNELS, Channel, Severity } from '../rules/ruleTypes';
import type { Person } from '../shared/types';
import type { PersonInput } from './peopleApi';
import { SEVERITY_LABEL, SEVERITY_ORDER, SEVERITY_STYLE } from './describePerson';

// Channels that can be limited to working hours (UI is always on)
const TIMED_CHANNELS: Channel[] = ['sms', 'phone', 'email'];

interface QuietRow {
  enabled: boolean;
  from: string;
  to: string;
  else: Channel;
}

const DEFAULT_PREFS: Person['channel_prefs'] = {
  critical: ['phone', 'sms'],
  warning: ['email'],
  info: ['ui'],
};

interface Props {
  initial?: Person;          // missing = new person
  teams: string[];           // departments from Admin & Invites
  onSave: (person: PersonInput) => Promise<string | null>; // returns an error message or null
  onCancel: () => void;
}

const inputClass =
  'w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500';
const labelClass = 'block text-xs font-semibold text-slate-300 mb-1';

export default function PersonForm({ initial, teams, onSave, onCancel }: Props) {
  const [name, setName] = useState(initial?.name ?? '');
  const [team, setTeam] = useState(initial?.team ?? '');
  const [email, setEmail] = useState(initial?.email ?? '');
  const [phone, setPhone] = useState(initial?.phone ?? '');
  const [onCall, setOnCall] = useState(initial?.on_call ?? false);
  const [isLead, setIsLead] = useState(initial?.role === 'lead');
  const [prefs, setPrefs] = useState<Person['channel_prefs']>(initial?.channel_prefs ?? DEFAULT_PREFS);
  const [quiet, setQuiet] = useState<Record<string, QuietRow>>(() =>
    Object.fromEntries(
      TIMED_CHANNELS.map((ch) => {
        const w = initial?.quiet_hours?.[ch];
        return [ch, {
          enabled: Boolean(w),
          from: w?.from ?? '08:00',
          to: w?.to ?? '20:00',
          else: (w?.else as Channel) ?? (ch === 'email' ? 'ui' : 'email'),
        }];
      }),
    ),
  );
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  function toggle(sev: Severity, ch: Channel) {
    const current = prefs[sev] ?? [];
    const next = current.includes(ch) ? current.filter((c) => c !== ch) : [...current, ch];
    setPrefs({ ...prefs, [sev]: next });
  }

  function updateQuiet(ch: Channel, change: Partial<QuietRow>) {
    setQuiet({ ...quiet, [ch]: { ...quiet[ch], ...change } });
  }

  // Builds the request body from the current form state
  function build(): PersonInput {
    const channelPrefs: Person['channel_prefs'] = {};
    for (const sev of SEVERITY_ORDER) {
      if ((prefs[sev] ?? []).length) channelPrefs[sev] = prefs[sev];
    }
    const quietHours: Person['quiet_hours'] = {};
    for (const ch of TIMED_CHANNELS) {
      const row = quiet[ch];
      if (row.enabled) quietHours[ch] = { from: row.from, to: row.to, else: row.else };
    }
    return {
      name: name.trim(),
      team: team.trim(),
      email: email.trim() || null,
      phone: phone.trim() || null,
      on_call: onCall,
      role: isLead ? 'lead' : 'member',
      channel_prefs: channelPrefs,
      quiet_hours: quietHours,
    };
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const person = build();
    if (!person.name) return setError('Enter a name.');
    if (!person.team) return setError('Enter a team.');
    const used = new Set(Object.values(person.channel_prefs).flat());
    if ((used.has('sms') || used.has('phone')) && !person.phone) return setError('SMS / phone call is selected – add a phone number.');
    if (used.has('email') && !person.email) return setError('E-mail is selected – add an e-mail address.');
    setError('');
    setSaving(true);
    try {
      const failure = await onSave(person);
      if (failure) setError(failure);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-white">{initial ? `Edit ${initial.name}` : 'Add person'}</h2>
        <button type="button" onClick={onCancel} className="text-slate-400 hover:text-white">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* 1. Who */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Name</label>
          <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Anna" />
        </div>
        <div>
          <label className={labelClass}>Team</label>
          <select className={inputClass} value={team} onChange={(e) => setTeam(e.target.value)}>
            <option value="">Choose a team…</option>
            {/* keep an old value visible if the department was renamed or removed */}
            {team && !teams.includes(team) && <option value={team}>{team} (not in Admin & Invites)</option>}
            {teams.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <p className="text-xs text-slate-500 mt-1">Teams are managed in Admin & Invites</p>
        </div>
        <div>
          <label className={labelClass}>E-mail</label>
          <input type="email" className={inputClass} value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder="anna@example.com" />
        </div>
        <div>
          <label className={labelClass}>Phone (for SMS and calls)</label>
          <input className={inputClass} value={phone} onChange={(e) => setPhone(e.target.value)}
            placeholder="+48 600 000 000" />
        </div>
      </div>

      <label className="flex items-center gap-3 cursor-pointer select-none">
        <input type="checkbox" checked={onCall} onChange={(e) => setOnCall(e.target.checked)}
          className="w-4 h-4 accent-amber-500" />
        <span className="text-sm text-slate-200">
          On call <span className="text-slate-500">– only the on-call person gets phone calls; others get an SMS instead</span>
        </span>
      </label>

      <label className="flex items-center gap-3 cursor-pointer select-none">
        <input type="checkbox" checked={isLead} onChange={(e) => setIsLead(e.target.checked)}
          className="w-4 h-4 accent-amber-500" />
        <span className="text-sm text-slate-200">
          Team lead <span className="text-slate-500">– approves risky runbook steps for this team</span>
        </span>
      </label>

      {/* 2. Channels per severity */}
      <div>
        <span className={labelClass}>How should alerts reach this person?</span>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 text-xs">
                <th className="text-left font-semibold py-2 pr-4">Severity</th>
                {CHANNELS.map((c) => <th key={c.value} className="font-semibold py-2 px-3">{c.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {SEVERITY_ORDER.map((sev) => (
                <tr key={sev} className="border-t border-slate-800">
                  <td className="py-2 pr-4">
                    <span className={`text-xs border px-2 py-0.5 rounded ${SEVERITY_STYLE[sev]}`}>{SEVERITY_LABEL[sev]}</span>
                  </td>
                  {CHANNELS.map((c) => (
                    <td key={c.value} className="text-center py-2 px-3">
                      <input type="checkbox" aria-label={`${SEVERITY_LABEL[sev]} via ${c.label}`}
                        checked={(prefs[sev] ?? []).includes(c.value)} onChange={() => toggle(sev, c.value)}
                        className="w-4 h-4 accent-amber-500" />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-slate-500 mt-1">
          The rule decides which channels are allowed; these preferences pick from them. A row with nothing ticked uses the rule's channels.
        </p>
      </div>

      {/* 3. Quiet hours */}
      <div>
        <span className={labelClass}>Working hours (optional)</span>
        <div className="space-y-2">
          {TIMED_CHANNELS.map((ch) => {
            const row = quiet[ch];
            const label = CHANNELS.find((c) => c.value === ch)?.label ?? ch;
            return (
              <div key={ch} className="flex items-center gap-2 flex-wrap text-sm text-slate-300">
                <label className="flex items-center gap-2 w-52 cursor-pointer whitespace-nowrap">
                  <input type="checkbox" checked={row.enabled} onChange={(e) => updateQuiet(ch, { enabled: e.target.checked })}
                    className="w-4 h-4 accent-amber-500" />
                  <span>{label} only between</span>
                </label>
                <input type="time" disabled={!row.enabled} value={row.from} onChange={(e) => updateQuiet(ch, { from: e.target.value })}
                  className={`${inputClass} w-32 disabled:opacity-40`} />
                <span>and</span>
                <input type="time" disabled={!row.enabled} value={row.to} onChange={(e) => updateQuiet(ch, { to: e.target.value })}
                  className={`${inputClass} w-32 disabled:opacity-40`} />
                <span>, otherwise</span>
                <select disabled={!row.enabled} value={row.else} onChange={(e) => updateQuiet(ch, { else: e.target.value as Channel })}
                  className={`${inputClass} w-36 disabled:opacity-40`}>
                  {CHANNELS.filter((c) => c.value !== ch).map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
              </div>
            );
          })}
        </div>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="flex justify-end gap-3">
        <button type="button" onClick={onCancel}
          className="px-4 py-2 rounded-lg text-sm text-slate-300 border border-slate-700 hover:bg-slate-800">
          Cancel
        </button>
        <button type="submit" disabled={saving}
          className="px-4 py-2 rounded-lg text-sm font-bold bg-amber-500 hover:bg-amber-400 text-slate-950 disabled:opacity-60">
          {saving ? 'Saving…' : 'Save person'}
        </button>
      </div>
    </form>
  );
}
