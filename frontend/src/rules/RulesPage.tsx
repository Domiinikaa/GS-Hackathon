// Rules page: list of rules + add, edit, enable/disable, delete.
// Data comes from /api/rules; changes take effect immediately, without a server restart.
import { useEffect, useMemo, useState } from 'react';
import { Pencil, Plus, RefreshCw, Search, Trash2 } from 'lucide-react';
import { CHANNELS, COLOR_DOT, Rule } from './ruleTypes';
import { describeRule } from './describeRule';
import { errorMessage, rulesApi } from './rulesApi';
import RuleForm from './RuleForm';

export default function RulesPage() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [filter, setFilter] = useState('');
  // null = form closed, 'new' = new rule, Rule = editing that rule
  const [editing, setEditing] = useState<Rule | 'new' | null>(null);

  async function load() {
    setLoading(true);
    setError('');
    try {
      setRules(await rulesApi.list());
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

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return rules;
    return rules.filter((r) => `${r.name} ${r.team} ${r.title}`.toLowerCase().includes(q));
  }, [rules, filter]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Alert rules</h1>
          <p className="text-sm text-slate-400">Decide which events reach which people, and on which channels.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} title="Reload" className="text-slate-400 hover:text-white p-2">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          {editing === null && (
            <button onClick={() => setEditing('new')}
              className="flex items-center space-x-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold px-4 py-2 rounded-lg text-sm">
              <Plus className="w-4 h-4" /><span>New rule</span>
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
        <RuleForm
          key={editing === 'new' ? 'new' : editing.id}
          initial={editing === 'new' ? undefined : editing}
          onSave={saveRule}
          onCancel={() => setEditing(null)}
        />
      )}

      {rules.length > 3 && (
        <div className="relative">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by name, team or title"
            className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500" />
        </div>
      )}

      <div className="space-y-3">
        {visible.map((rule) => (
          <div key={rule.id}
            className={`bg-slate-900 border border-slate-800 rounded-xl p-5 flex gap-4 ${rule.enabled ? '' : 'opacity-50'}`}>
            <span className={`w-3 h-3 rounded-full mt-1.5 shrink-0 ${COLOR_DOT[rule.color] ?? 'bg-slate-500'}`} />
            <div className="flex-1 space-y-2 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="font-bold text-white">{rule.name}</h3>
                <span className="text-xs text-slate-400 bg-slate-800 px-2 py-0.5 rounded">{rule.team}</span>
                <span className="text-xs uppercase text-slate-500">{rule.severity}</span>
              </div>
              <p className="text-sm text-slate-300">{describeRule(rule)}</p>
              <div className="flex gap-2 flex-wrap">
                {rule.channels.map((ch) => (
                  <span key={ch} className="text-xs bg-slate-800 border border-slate-700 text-slate-300 px-2 py-0.5 rounded">
                    {CHANNELS.find((c) => c.value === ch)?.label ?? ch}
                  </span>
                ))}
                <span className="text-xs font-mono text-slate-500 break-all">title: {rule.title}</span>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <button onClick={() => toggleEnabled(rule)}
                className={`text-xs px-2 py-1 rounded border ${
                  rule.enabled ? 'border-emerald-500/50 text-emerald-400' : 'border-slate-600 text-slate-400'
                }`}>
                {rule.enabled ? 'Enabled' : 'Disabled'}
              </button>
              <button onClick={() => setEditing(rule)} className="text-slate-400 hover:text-white" title="Edit">
                <Pencil className="w-4 h-4" />
              </button>
              <button onClick={() => deleteRule(rule)} className="text-slate-400 hover:text-red-400" title="Delete">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
        {!loading && rules.length === 0 && !error && (
          <p className="text-center text-slate-500 py-8">No rules yet. Create the first one!</p>
        )}
        {!loading && rules.length > 0 && visible.length === 0 && (
          <p className="text-center text-slate-500 py-8">No rules match “{filter}”.</p>
        )}
      </div>
    </div>
  );
}
