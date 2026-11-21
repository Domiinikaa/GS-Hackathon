// Rules page.
import { useEffect, useMemo, useState } from 'react';
import { Plus, RefreshCw, Search } from 'lucide-react';
import { Rule } from './ruleTypes';
import RuleCard from './RuleCard';
import { RunbookSummary, errorMessage, rulesApi } from './rulesApi';
import RuleForm from './RuleForm';

export default function RulesPage() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [runbooks, setRunbooks] = useState<RunbookSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [filter, setFilter] = useState('');
  // null = form closed, 'new' = new rule, Rule = editing that rule
  const [editing, setEditing] = useState<Rule | 'new' | null>(null);
  // ids of rules whose details are expanded
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());

  function toggleOpen(id: string) {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [rulesList, runbooksList] = await Promise.all([
        rulesApi.list(),
        rulesApi.runbooks().catch(() => [] as RunbookSummary[]),
      ]);
      setRules(rulesList);
      setRunbooks(runbooksList);
    } catch (e) {
      setError(`Could not load rules: ${errorMessage(e)}`);
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

  // Returns an error message to show in the form, or null on success
  async function saveRule(rule: Rule): Promise<string | null> {
    try {
      const isNew = editing === 'new';
      const saved = isNew ? await rulesApi.create(rule) : await rulesApi.update(rule);
      setRules((prev) => (isNew ? [...prev, saved] : prev.map((r) => (r.id === saved.id ? saved : r))));
      setEditing(null);
      flash(isNew ? `Rule "${saved.name}" created.` : `Rule "${saved.name}" saved.`);
      return null;
    } catch (e) {
      return errorMessage(e);
    }
  }

  async function deleteRule(rule: Rule) {
    if (!window.confirm(`Delete rule "${rule.name}"?`)) return;
    try {
      const res = await rulesApi.remove(rule.id);
      if (res.deleted) {
        setRules((prev) => prev.filter((r) => r.id !== rule.id));
        flash(`Rule "${rule.name}" deleted.`);
      } else {
        setRules((prev) => prev.map((r) => (r.id === rule.id ? { ...r, enabled: false } : r)));
        flash(res.detail ?? 'Rule disabled.');
      }
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function toggleEnabled(rule: Rule) {
    try {
      const saved = await rulesApi.setEnabled(rule.id, !rule.enabled);
      setRules((prev) => prev.map((r) => (r.id === saved.id ? saved : r)));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  const runbookNameById = useMemo(
    () => new Map(runbooks.map((rb) => [rb.id, rb.name])),
    [runbooks],
  );

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return rules;
    return rules.filter((r) => `${r.name} ${r.team} ${r.title}`.toLowerCase().includes(q));
  }, [rules, filter]);

  const enabledCount = rules.filter((r) => r.enabled).length;
  const allOpen = visible.length > 0 && visible.every((r) => openIds.has(r.id));

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-ink">Alert rules</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Decide which events reach which people, and on which channels.
            {rules.length > 0 && ` ${enabledCount} of ${rules.length} rules are on.`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {visible.length > 0 && (
            <button
              onClick={() => setOpenIds(allOpen ? new Set() : new Set(visible.map((r) => r.id)))}
              className="text-sm font-medium text-ink-muted hover:text-ink px-3 py-2 rounded-full hover:bg-white/5"
            >
              {allOpen ? 'Collapse all' : 'Expand all'}
            </button>
          )}
          <button onClick={load} title="Reload rules" aria-label="Reload rules"
            className="w-10 h-10 rounded-full flex items-center justify-center text-ink-muted hover:text-ink hover:bg-white/5">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          {editing === null && (
            <button onClick={() => setEditing('new')} className="btn-primary flex items-center gap-2 px-4 h-10 text-sm">
              <Plus className="w-4 h-4" />New rule
            </button>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="text-sm text-signal-critical bg-signal-critical/10 rounded-xl px-4 py-2.5">{error}</p>
      )}
      {notice && (
        <p role="status" className="text-sm text-signal-clear bg-signal-clear/10 rounded-xl px-4 py-2.5">{notice}</p>
      )}

      {editing !== null && (
        <RuleForm
          key={editing === 'new' ? 'new' : editing.id}
          initial={editing === 'new' ? undefined : editing}
          onSave={saveRule}
          onCancel={() => setEditing(null)}
        />
      )}

      {rules.length > 3 && (
        <div className="relative">
          <Search className="w-4 h-4 text-ink-muted absolute left-4 top-1/2 -translate-y-1/2" />
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by name, team or headline"
            aria-label="Filter rules"
            className="field w-full h-11 pl-10 pr-4 text-sm" />
        </div>
      )}

      <div className="space-y-3">
        {visible.map((rule) => (
          <RuleCard
            key={rule.id}
            rule={rule}
            runbookName={rule.runbook_id ? runbookNameById.get(rule.runbook_id) : undefined}
            open={openIds.has(rule.id)}
            onToggleOpen={() => toggleOpen(rule.id)}
            onToggleEnabled={() => toggleEnabled(rule)}
            onEdit={() => setEditing(rule)}
            onDelete={() => deleteRule(rule)}
          />
        ))}
        {!loading && rules.length === 0 && !error && (
          <div className="surface p-10 text-center">
            <p className="text-ink font-medium">No rules yet</p>
            <p className="mt-1 text-sm text-ink-muted">Create a rule to start turning events into alerts.</p>
          </div>
        )}
        {!loading && rules.length > 0 && visible.length === 0 && (
          <p className="text-center text-ink-muted py-8">No rules match “{filter}”.</p>
        )}
      </div>
    </div>
  );
}
