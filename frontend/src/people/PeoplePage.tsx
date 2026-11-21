// People page.
import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Clock, Mail, Pencil, Phone, Plus, RefreshCw, Trash2, Users } from 'lucide-react';
import { ChannelPill, EmptyState, Notice, PageHeader, SEVERITY_DOT, type SeverityLevel, Toggle, cn, iconButton } from '../shared/ui';
import type { Person } from '../shared/types';
import { errorMessage } from '../rules/rulesApi';
import { PersonInput, peopleApi } from './peopleApi';
import { SEVERITY_LABEL, SEVERITY_ORDER, describeQuietHours } from './describePerson';
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

  // Teams used on this page (for the filter) and all teams from Admin & Teams (for the form)
  const teams = useMemo(() => [...new Set(people.map((p) => p.team))].sort(), [people]);
  const [allTeams, setAllTeams] = useState<string[]>([]);
  useEffect(() => {
    peopleApi.teams().then((t) => setAllTeams(t.teams)).catch(() => {});
  }, []);
  const availableTeams = useMemo(() => [...new Set([...allTeams, ...teams])].filter(Boolean).sort(), [allTeams, teams]);

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
      <PageHeader
        title="People"
        description="Team members, who is on call, and how each person wants to be reached."
        actions={<>
          <button onClick={load} title="Reload people" aria-label="Reload people" className={iconButton}>
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          {editing === null && (
            <button onClick={() => setEditing('new')} className="btn-primary flex items-center gap-2 px-4 h-10 text-sm">
              <Plus className="w-4 h-4" />Add person
            </button>
          )}
        </>}
      />

      {error && <Notice tone="error">{error}</Notice>}
      {notice && <Notice tone="success">{notice}</Notice>}

      {editing !== null && (
        <PersonForm
          key={editing === 'new' ? 'new' : editing.id}
          initial={editing === 'new' ? undefined : editing}
          teams={availableTeams}
          onSave={savePerson}
          onCancel={() => setEditing(null)}
        />
      )}

      {teams.length > 1 && (
        <div className="glass-pill p-1 gap-1 flex-wrap !rounded-2xl sm:!rounded-full w-fit max-w-full" role="group" aria-label="Filter by team">
          {['all', ...teams].map((t) => (
            <button key={t} onClick={() => setTeamFilter(t)} aria-pressed={teamFilter === t}
              className={cn('px-3.5 h-8 rounded-full text-sm transition-all duration-300 border',
                teamFilter === t
                  ? 'bg-white/[0.12] border-white/20 text-white font-medium shadow-[inset_0_1px_1px_rgba(255,255,255,0.14)]'
                  : 'border-transparent text-ink-muted hover:text-white')}>
              {t === 'all' ? 'All teams' : t}
              <span className="ml-1.5 text-xs text-ink-muted tabular-nums">
                {t === 'all' ? people.length : people.filter((p) => p.team === t).length}
              </span>
            </button>
          ))}
        </div>
      )}

      {grouped.map(([team, members]) => (
        <section key={team} className="space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-lg font-semibold text-white">{team}</h2>
            <span className="text-sm text-ink-muted">{members.length} {members.length === 1 ? 'person' : 'people'}</span>
            {!members.some((m) => m.on_call) && (
              <span className="inline-flex items-center gap-1 text-xs text-amber-200 bg-amber-500/10 border border-amber-500/25 px-2.5 py-0.5 rounded-full"
                title="Phone-call alerts go only to the on-call person">
                <AlertTriangle className="w-3 h-3" />Nobody on call, phone alerts fall back to SMS
              </span>
            )}
            {!members.some((m) => m.role === 'lead') && (
              <span className="inline-flex items-center gap-1 text-xs text-amber-200 bg-amber-500/10 border border-amber-500/25 px-2.5 py-0.5 rounded-full"
                title="Risky runbook steps need approval from the team lead">
                <AlertTriangle className="w-3 h-3" />No team lead, risky steps can't be approved
              </span>
            )}
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            {members.map((person) => {
              const quiet = describeQuietHours(person);
              return (
                <article key={person.id} className="glass-card p-5 flex gap-4">
                  <span className={cn('w-11 h-11 rounded-full flex items-center justify-center shrink-0 text-sm font-semibold text-white ring-1 ring-white/15 shadow-[inset_0_1px_1px_rgba(255,255,255,0.2)]',
                    person.on_call ? 'bg-gradient-to-br from-emerald-400/40 to-sky-500/30' : 'bg-gradient-to-br from-indigo-400/30 to-slate-500/20')}
                    aria-hidden="true">
                    {initials(person.name)}
                  </span>

                  <div className="flex-1 space-y-3 min-w-0">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="text-[16px] font-semibold text-white">{person.name}</h3>
                          {person.role === 'lead' && (
                            <span className="text-xs font-medium text-violet-200 bg-violet-500/10 border border-violet-500/30 px-2 py-0.5 rounded-full"
                              title="Approves risky runbook steps for this team">
                              Team lead
                            </span>
                          )}
                        </div>
                        <div className="mt-1 flex gap-x-4 gap-y-1 flex-wrap text-[13px] text-ink-muted">
                          <span className="flex items-center gap-1.5 min-w-0"><Mail className="w-3.5 h-3.5 shrink-0" /><span className="truncate">{person.email ?? 'No email'}</span></span>
                          <span className="flex items-center gap-1.5"><Phone className="w-3.5 h-3.5 shrink-0" />{person.phone ?? 'No phone'}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-0.5 shrink-0 -mr-2 -mt-1">
                        <button onClick={() => setEditing(person)} className={iconButton} title="Edit" aria-label={`Edit ${person.name}`}>
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button onClick={() => deletePerson(person)} className={cn(iconButton, 'hover:text-rose-300 hover:bg-rose-500/10')}
                          title="Remove" aria-label={`Remove ${person.name}`}>
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    <div className="surface-well p-3 space-y-2">
                      {SEVERITY_ORDER.map((sev) => {
                        const chans = person.channel_prefs?.[sev] ?? [];
                        return (
                          <div key={sev} className="flex items-center gap-2 flex-wrap">
                            <span className="w-20 shrink-0 flex items-center gap-1.5 text-xs text-ink-muted">
                              <span className={cn('w-1.5 h-1.5 rounded-full', SEVERITY_DOT[sev as SeverityLevel] ?? 'bg-slate-400')} />
                              {SEVERITY_LABEL[sev]}
                            </span>
                            {chans.length
                              ? chans.map((c) => <ChannelPill key={c} channel={c} />)
                              : <span className="text-xs text-ink-muted">Uses the rule's channels</span>}
                          </div>
                        );
                      })}
                    </div>

                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <div className="text-xs text-ink-muted space-y-0.5 min-w-0">
                        {quiet.length > 0
                          ? quiet.map((q) => <p key={q} className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 shrink-0" />{q}</p>)
                          : <p className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 shrink-0" />Reachable any time</p>}
                      </div>
                      <label className="flex items-center gap-2.5 text-sm text-slate-200 cursor-pointer"
                        title="Phone-call alerts go only to the on-call person">
                        <span className={person.on_call ? 'text-emerald-300 font-medium' : ''}>On call</span>
                        <Toggle checked={!!person.on_call} onChange={() => toggleOnCall(person)}
                          label={`${person.name}: ${person.on_call ? 'on call, turn off' : 'off call, turn on'}`} />
                      </label>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ))}

      {!loading && people.length === 0 && !error && (
        <EmptyState icon={Users} title="No people yet" text="Add the first person so alerts have somewhere to go."
          action={<button onClick={() => setEditing('new')} className="btn-primary flex items-center gap-2 px-4 h-10 text-sm"><Plus className="w-4 h-4" />Add person</button>} />
      )}
    </div>
  );
}

function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join('');
}
