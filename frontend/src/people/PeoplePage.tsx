// People page: team members and their channel preferences (critical → phone + SMS, warning → email, info → UI, working hours).
// Data comes from /api/people; alert delivery reads these preferences in services/people_service.py.
import { useEffect, useMemo, useState } from 'react';
import { Clock, Mail, Pencil, Phone, Plus, RefreshCw, Trash2, UserRound } from 'lucide-react';
import type { Person } from '../shared/types';
import { errorMessage } from '../rules/rulesApi';
import { PersonInput, peopleApi } from './peopleApi';
import { SEVERITY_LABEL, SEVERITY_ORDER, SEVERITY_STYLE, channelLabel, describeQuietHours } from './describePerson';
import PersonForm from './PersonForm';

function toInput(p: Person): PersonInput {
  const { id: _id, ...rest } = p;
  return rest;
}

export default function PeoplePage() {
  const [people, setPeople] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [teamFilter, setTeamFilter] = useState<string>('all');
  // null = form closed, 'new' = new person, Person = editing that person
  const [editing, setEditing] = useState<Person | 'new' | null>(null);

  async function load() {
    setLoading(true);
    setError('');
    try {
      setPeople(await peopleApi.list());
    } catch (e) {
      setError(`Could not load people: ${errorMessage(e)}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function flash(text: string) {
    setNotice(text);
    window.setTimeout(() => setNotice(''), 3000);
  }

  async function savePerson(input: PersonInput): Promise<string | null> {
    try {
      if (editing === 'new') {
        const saved = await peopleApi.create(input);
        setPeople((prev) => [...prev, saved]);
        flash(`${saved.name} added to ${saved.team}.`);
      } else if (editing) {
        const saved = await peopleApi.update(editing.id, input);
        setPeople((prev) => prev.map((p) => (p.id === saved.id ? saved : p)));
        flash(`${saved.name} saved.`);
      }
      setEditing(null);
      return null;
    } catch (e) {
      return errorMessage(e);
    }
  }

  async function deletePerson(person: Person) {
    if (!window.confirm(`Remove ${person.name} from ${person.team}? They will stop receiving alerts.`)) return;
    try {
      await peopleApi.remove(person.id);
      setPeople((prev) => prev.filter((p) => p.id !== person.id));
      flash(`${person.name} removed.`);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function toggleOnCall(person: Person) {
    try {
      const saved = await peopleApi.update(person.id, { ...toInput(person), on_call: !person.on_call });
      setPeople((prev) => prev.map((p) => (p.id === saved.id ? saved : p)));
      flash(saved.on_call ? `${saved.name} is now on call.` : `${saved.name} is no longer on call.`);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  const teams = useMemo(() => [...new Set(people.map((p) => p.team))].sort(), [people]);

  // People grouped by team (after applying the team filter)
  const grouped = useMemo(() => {
    const visible = teamFilter === 'all' ? people : people.filter((p) => p.team === teamFilter);
    const map = new Map<string, Person[]>();
    for (const p of [...visible].sort((a, b) => a.name.localeCompare(b.name))) {
      map.set(p.team, [...(map.get(p.team) ?? []), p]);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [people, teamFilter]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">People & channels</h1>
          <p className="text-sm text-slate-400">Who is in each team, and how each person wants to be alerted.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} title="Reload" className="text-slate-400 hover:text-white p-2">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          {editing === null && (
            <button onClick={() => setEditing('new')}
              className="flex items-center space-x-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold px-4 py-2 rounded-lg text-sm">
              <Plus className="w-4 h-4" /><span>Add person</span>
            </button>
          )}
        </div>
      </div>

      {error && (
        <p className="text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">{error}</p>
      )}
      {notice && (
        <p className="text-sm text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-lg px-3 py-2">{notice}</p>
      )}

      {editing !== null && (
        <PersonForm
          key={editing === 'new' ? 'new' : editing.id}
          initial={editing === 'new' ? undefined : editing}
          teams={teams}
          onSave={savePerson}
          onCancel={() => setEditing(null)}
        />
      )}

      {teams.length > 1 && (
        <div className="flex gap-2 flex-wrap">
          {['all', ...teams].map((t) => (
            <button key={t} onClick={() => setTeamFilter(t)}
              className={`px-3 py-1 rounded-lg text-sm border ${
                teamFilter === t ? 'bg-amber-500/20 border-amber-500 text-amber-300' : 'border-slate-700 text-slate-400 hover:border-slate-500'
              }`}>
              {t === 'all' ? `All teams (${people.length})` : `${t} (${people.filter((p) => p.team === t).length})`}
            </button>
          ))}
        </div>
      )}

      {grouped.map(([team, members]) => (
        <section key={team} className="space-y-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-bold uppercase tracking-wide text-slate-400">{team}</h2>
            {!members.some((m) => m.on_call) && (
              <span className="text-xs text-amber-300/80" title="Phone-call alerts go only to the on-call person">
                · nobody on call – phone alerts fall back to SMS
              </span>
            )}
          </div>

          {members.map((person) => {
            const quiet = describeQuietHours(person);
            return (
              <div key={person.id} className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex gap-4">
                <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center shrink-0">
                  <UserRound className="w-5 h-5 text-slate-400" />
                </div>

                <div className="flex-1 space-y-3 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="font-bold text-white">{person.name}</h3>
                    {person.on_call && (
                      <span className="text-xs font-bold text-emerald-300 bg-emerald-500/10 border border-emerald-500/40 px-2 py-0.5 rounded">
                        ON CALL
                      </span>
                    )}
                  </div>

                  <div className="flex gap-4 flex-wrap text-sm text-slate-400">
                    <span className="flex items-center gap-1"><Mail className="w-3.5 h-3.5" />{person.email ?? '—'}</span>
                    <span className="flex items-center gap-1"><Phone className="w-3.5 h-3.5" />{person.phone ?? '—'}</span>
                  </div>

                  <div className="flex gap-2 flex-wrap">
                    {SEVERITY_ORDER.map((sev) => {
                      const chans = person.channel_prefs?.[sev] ?? [];
                      return (
                        <span key={sev} className={`text-xs border px-2 py-1 rounded ${SEVERITY_STYLE[sev]}`}>
                          <b>{SEVERITY_LABEL[sev]}</b> → {chans.length ? chans.map(channelLabel).join(' + ') : 'rule channels'}
                        </span>
                      );
                    })}
                  </div>

                  {quiet.length > 0 && (
                    <div className="text-xs text-slate-400 space-y-0.5">
                      {quiet.map((q) => (
                        <p key={q} className="flex items-center gap-1"><Clock className="w-3.5 h-3.5" />{q}</p>
                      ))}
                    </div>
                  )}
                </div>

                <div className="flex items-start gap-3">
                  <button onClick={() => toggleOnCall(person)}
                    title="Phone-call alerts go only to the on-call person"
                    aria-label={`${person.name}: ${person.on_call ? 'on call, click to take off call' : 'off call, click to put on call'}`}
                    className={`text-xs px-2 py-1 rounded border whitespace-nowrap ${
                      person.on_call ? 'border-emerald-500/50 text-emerald-400' : 'border-slate-600 text-slate-400'
                    }`}>
                    {person.on_call ? 'On call' : 'Off call'}
                  </button>
                  <button onClick={() => setEditing(person)} className="text-slate-400 hover:text-white" title="Edit">
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button onClick={() => deletePerson(person)} className="text-slate-400 hover:text-red-400" title="Remove">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            );
          })}
        </section>
      ))}

      {!loading && people.length === 0 && !error && (
        <p className="text-center text-slate-500 py-8">No people yet. Add the first person so alerts have somewhere to go.</p>
      )}
    </div>
  );
}
