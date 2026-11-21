// Add / edit person form.
import React, { useState } from 'react';
import { X } from 'lucide-react';
import { CHANNELS, Channel, Severity } from '../rules/ruleTypes';
import type { Person } from '../shared/types';
import type { PersonInput } from './peopleApi';
import { SEVERITY_LABEL, SEVERITY_ORDER, SEVERITY_STYLE } from './describePerson';

// Channels that can be limited to working hours (UI is always on)
const TIMED_CHANNELS: Channel[] = ['sms', 'phone', 'email'];
// The app feed is always on, so people only choose their personal channels
const PERSONAL_CHANNELS = CHANNELS.filter((c) => c.value !== 'ui');

interface QuietRow {
  enabled: boolean;
  from: string;
  to: string;
  else: Channel;
}

const DEFAULT_PREFS: Person['channel_prefs'] = {
  critical: ['email', 'phone', 'sms'],
  warning: ['email'],
  info: [],
};

interface Props {
  initial?: Person;          // missing = new person
  teams: string[];           // teams from Admin & Teams
  onSave: (person: PersonInput) => Promise<string | null>; // returns an error message or null
  onCancel: () => void;
  canEditAdminFields?: boolean; // false = regular user editing own profile: e-mail and team lead are locked
}

const inputClass =
  'field w-full px-3 py-2 text-sm';
const labelClass = 'block text-xs font-semibold text-slate-300 mb-1';

export default function PersonForm({ initial, teams, onSave, onCancel, canEditAdminFields = true }: Props) {
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
    <form onSubmit={handleSubmit} className="glass-card glass-card--static p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">{initial ? `Edit ${initial.name}` : 'Add person'}</h2>
        <button type="button" onClick={onCancel} className="text-ink-muted hover:text-white">
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
            {/* keep an old value visible if the team was renamed or removed */}
            {team && !teams.includes(team) && <option value={team}>{team} (not in Lead &amp; Teams)</option>}
            {teams.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <p className="text-xs text-slate-500 mt-1">Teams are managed in Lead &amp; Teams</p>
        </div>
        <div>
          <label className={labelClass}>E-mail</label>
          <input type="email" className={`${inputClass} disabled:opacity-60 disabled:cursor-not-allowed`} value={email}
            onChange={(e) => setEmail(e.target.value)} placeholder="anna@example.com" disabled={!canEditAdminFields} />
          {!canEditAdminFields && (
            <p className="text-xs text-slate-500 mt-1">Your login e-mail – only an administrator can change it</p>
          )}
        </div>
        <div>
          <label className={labelClass}>Phone (for SMS and calls)</label>
          <input className={inputClass} value={phone} onChange={(e) => setPhone(e.target.value)}
            placeholder="+48 600 000 000" />
        </div>
      </div>

      <label className="flex items-center gap-3 cursor-pointer select-none">
        <input type="checkbox" checked={onCall} onChange={(e) => setOnCall(e.target.checked)}
          className="w-4 h-4 accent-ios-blue" />
        <span className="text-sm text-slate-200">
          On call <span className="text-slate-500">– only the on-call person gets phone calls; others get an SMS instead</span>
        </span>
      </label>

      <label className={`flex items-center gap-3 select-none ${canEditAdminFields ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}>
        <input type="checkbox" checked={isLead} onChange={(e) => setIsLead(e.target.checked)}
          disabled={!canEditAdminFields} className="w-4 h-4 accent-ios-blue" />
        <span className="text-sm text-slate-200">
          Team lead <span className="text-slate-500">
            – approves risky runbook steps &amp; manages teams/leads{!canEditAdminFields && ' (set by an administrator)'}
          </span>
        </span>
      </label>

      {/* 2. Channels per severity */}
      <div>
        <span className={labelClass}>How should alerts reach this person?</span>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-ink-muted text-xs">
                <th className="text-left font-semibold py-2 pr-4">Severity</th>
                {PERSONAL_CHANNELS.map((c) => <th key={c.value} className="font-semibold py-2 px-3">{c.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {SEVERITY_ORDER.map((sev) => (
                <tr key={sev} className="border-t border-white/[0.08]">
                  <td className="py-2 pr-4">
                    <span className={`text-xs border px-2 py-0.5 rounded ${SEVERITY_STYLE[sev]}`}>{SEVERITY_LABEL[sev]}</span>
                  </td>
                  {PERSONAL_CHANNELS.map((c) => (
                    <td key={c.value} className="text-center py-2 px-3">
                      <input type="checkbox" aria-label={`${SEVERITY_LABEL[sev]} via ${c.label}`}
                        checked={(prefs[sev] ?? []).includes(c.value)} onChange={() => toggle(sev, c.value)}
                        className="w-4 h-4 accent-ios-blue" />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-slate-500 mt-1">
          Every alert also appears in the team feed in the app. A row with nothing ticked uses the default: phone and SMS for critical, email for warning, app only for info.
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
                    className="w-4 h-4 accent-ios-blue" />
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
                  {CHANNELS.filter((c) => c.value !== ch).map((c) => <option key={c.value} value={c.value}>{c.value === 'ui' ? 'App only' : c.label}</option>)}
                </select>
              </div>
            );
          })}
        </div>
      </div>

      {error && <p className="text-sm text-rose-300">{error}</p>}

      <div className="flex justify-end gap-3">
        <button type="button" onClick={onCancel}
          className="px-4 py-2 rounded-lg text-sm text-slate-300 border border-white/10 hover:bg-white/[0.08]">
          Cancel
        </button>
        <button type="submit" disabled={saving}
          className="btn-primary px-4 py-2 text-sm disabled:opacity-60">
          {saving ? 'Saving…' : 'Save person'}
        </button>
      </div>
    </form>
  );
}
