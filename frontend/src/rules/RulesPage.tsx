// Strona "Rules": lista reguł + dodawanie, edycja, włączanie/wyłączanie, usuwanie.
// Na razie działa na sztucznych danych (MOCK_RULES) – zmiany znikają po odświeżeniu strony.
import { useState } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { CHANNELS, COLOR_DOT, Rule } from './ruleTypes';
import { MOCK_RULES } from './mockRules';
import { describeRule } from './describeRule';
import RuleForm from './RuleForm';

export default function RulesPage() {
  const [rules, setRules] = useState<Rule[]>(MOCK_RULES);
  // null = formularz zamknięty, 'new' = nowa reguła, Rule = edycja tej reguły
  const [editing, setEditing] = useState<Rule | 'new' | null>(null);

  function saveRule(rule: Rule) {
    // TODO: POST /api/rules (nowa) albo PUT /api/rules/{id} (edycja)
    const exists = rules.some((r) => r.id === rule.id);
    setRules(exists ? rules.map((r) => (r.id === rule.id ? rule : r)) : [...rules, rule]);
    setEditing(null);
  }

  function deleteRule(id: string) {
    // TODO: DELETE /api/rules/{id}
    setRules(rules.filter((r) => r.id !== id));
  }

  function toggleEnabled(id: string) {
    // TODO: PUT /api/rules/{id}
    setRules(rules.map((r) => (r.id === id ? { ...r, enabled: !r.enabled } : r)));
  }

  return (
    <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Alert rules</h1>
            <p className="text-sm text-slate-400">Decide which events reach which people, and on which channels.</p>
          </div>
          {editing === null && (
            <button onClick={() => setEditing('new')}
              className="flex items-center space-x-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold px-4 py-2 rounded-lg text-sm">
              <Plus className="w-4 h-4" /><span>New rule</span>
            </button>
          )}
        </div>

        <p className="text-xs text-amber-400/80 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
          Demo data – not connected to the backend yet.
        </p>

        {editing !== null && (
          <RuleForm
            key={editing === 'new' ? 'new' : editing.id}
            initial={editing === 'new' ? undefined : editing}
            onSave={saveRule}
            onCancel={() => setEditing(null)}
          />
        )}

        <div className="space-y-3">
          {rules.map((rule) => (
            <div key={rule.id}
              className={`bg-slate-900 border border-slate-800 rounded-xl p-5 flex gap-4 ${rule.enabled ? '' : 'opacity-50'}`}>
              <span className={`w-3 h-3 rounded-full mt-1.5 shrink-0 ${COLOR_DOT[rule.color]}`} />
              <div className="flex-1 space-y-2">
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
                  <span className="text-xs font-mono text-slate-500">title: {rule.title}</span>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <button onClick={() => toggleEnabled(rule.id)}
                  className={`text-xs px-2 py-1 rounded border ${
                    rule.enabled ? 'border-emerald-500/50 text-emerald-400' : 'border-slate-600 text-slate-400'
                  }`}>
                  {rule.enabled ? 'Enabled' : 'Disabled'}
                </button>
                <button onClick={() => setEditing(rule)} className="text-slate-400 hover:text-white" title="Edit">
                  <Pencil className="w-4 h-4" />
                </button>
                <button onClick={() => deleteRule(rule.id)} className="text-slate-400 hover:text-red-400" title="Delete">
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
          {rules.length === 0 && <p className="text-center text-slate-500 py-8">No rules yet. Create the first one!</p>}
        </div>
    </div>
  );
}
