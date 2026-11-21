// People page.
import { useEffect, useMemo, useState } from 'react';
import { ChevronRight, Plus, RefreshCw, Users } from 'lucide-react';
import { ChannelList, EmptyState, Notice, PageHeader, Row, SEVERITY_DOT, Section, Segmented, type SeverityLevel, Toggle, cn, iconButton } from '../shared/ui';
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
  const [openId, setOpenId] = useState<number | null>(null);
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
            <button onClick={() => setEditing('new')} className="btn-primary flex items-center gap-1.5 px-4 h-9 text-[15px]">
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
        <Segmented
          label="Filter by team"
          value={teamFilter}
          onChange={setTeamFilter}
          options={[{ value: 'all', label: 'All teams' }, ...teams.map((t) => ({ value: t, label: t }))]}
        />
      )}

      <div className="space-y-7">
        {grouped.map(([team, members]) => {
          const warnings = [
            !members.some((m) => m.on_call) && 'Nobody is on call, so phone alerts fall back to SMS.',
            !members.some((m) => m.role === 'lead') && "No team lead, so risky runbook steps can't be approved.",
          ].filter(Boolean) as string[];
          return (
            <Section key={team} title={`${team}, ${members.length} ${members.length === 1 ? 'person' : 'people'}`}
              footer={warnings.length > 0 && <span className="text-ios-orange">{warnings.join(' ')}</span>}>
              {members.map((person) => (
                <PersonRow key={person.id} person={person} open={openId === person.id}
                  onToggleOpen={() => setOpenId(openId === person.id ? null : person.id)}
                  onToggleOnCall={() => toggleOnCall(person)}
                  onEdit={() => setEditing(person)}
                  onDelete={() => deletePerson(person)} />
              ))}
            </Section>
          );
        })}
      </div>

      {!loading && people.length === 0 && !error && (
        <EmptyState icon={Users} title="No people yet" text="Add the first person so alerts have somewhere to go."
          action={<button onClick={() => setEditing('new')} className="btn-primary flex items-center gap-1.5 px-4 h-9 text-[15px]"><Plus className="w-4 h-4" />Add person</button>} />
      )}
    </div>
  );
}

// What happens when a person has not chosen channels (matches DEFAULT_CHANNELS in people_service.py)
const DEFAULT_LABEL: Record<string, string> = {
  critical: 'Default: phone and SMS',
  warning: 'Default: email',
  info: 'App only',
};

function PersonRow({ person, open, onToggleOpen, onToggleOnCall, onEdit, onDelete }: {
  person: Person; open: boolean; onToggleOpen: () => void; onToggleOnCall: () => void; onEdit: () => void; onDelete: () => void;
}) {
  const quiet = describeQuietHours(person);
  return (
    <div className="ios-divided">
      <div className="ios-row">
        <button type="button" onClick={onToggleOpen} aria-expanded={open}
          className="flex-1 min-w-0 flex items-center gap-3 text-left">
          <span className="w-10 h-10 rounded-full bg-gradient-to-b from-[#8e8e93] to-[#636366] flex items-center justify-center shrink-0 text-[15px] font-semibold text-white"
            aria-hidden="true">
            {initials(person.name)}
          </span>
          <span className="min-w-0">
            <span className="block text-[15px] font-semibold text-white truncate">{person.name}</span>
            <span className="block text-[13px] text-ink-muted truncate">
              {person.role === 'lead' ? 'Team lead' : 'Member'}{person.on_call && <span className="text-ios-green">, on call</span>}
            </span>
          </span>
        </button>
        <Toggle checked={!!person.on_call} onChange={onToggleOnCall}
          label={`${person.name}: ${person.on_call ? 'on call, turn off' : 'off call, turn on'}`} />
        <button type="button" onClick={onToggleOpen} aria-label={open ? 'Hide details' : 'Show details'} className="p-1 -mr-1">
          <ChevronRight className={cn('w-4 h-4 text-ink-faint transition-transform duration-300', open && 'rotate-90')} />
        </button>
      </div>

      <div className="disclosure" data-open={open}>
        <div {...(open ? {} : ({ inert: '' } as Record<string, string>))}>
          <div className="bg-black/25 ios-divided" style={{ paddingLeft: 52 }}>
            <Row label="Email" value={person.email ?? 'Not set'} />
            <Row label="Phone" value={person.phone ?? 'Not set'} />
            {SEVERITY_ORDER.map((sev) => {
              const chans = (person.channel_prefs?.[sev] ?? []).filter((c) => c !== 'ui');
              return (
                <Row key={sev}
                  label={<span className="inline-flex items-center gap-2">
                    <span className={cn('w-2 h-2 rounded-full', SEVERITY_DOT[sev as SeverityLevel] ?? 'bg-ink-faint')} />
                    {SEVERITY_LABEL[sev]} alerts
                  </span>}
                  value={chans.length ? <ChannelList channels={chans} /> : <span>{DEFAULT_LABEL[sev] ?? 'Default'}</span>} />
              );
            })}
            <Row label="Quiet hours" value={quiet.length ? quiet.join(' ') : 'None'} />
            <div className="ios-row justify-between">
              <button type="button" onClick={onEdit} className="text-[15px] text-ios-blue hover:opacity-70">Edit</button>
              <button type="button" onClick={onDelete} className="text-[15px] text-ios-red hover:opacity-70">Remove</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join('');
}
