// OSOBA 4 – akcje, które aplikacja umie wykonać w krokach runbooka.
// Wbudowane (w kodzie) + własne zespołu: nazwa + adres + czy wymaga zgody. Nowa akcja = formularz, bez kodu
// (kartka 2.6: "Adding a new runbook or a new kind of action should be as easy as adding a rule").
import { useEffect, useState } from 'react';
import { Pencil, Plus, Trash2, Zap } from 'lucide-react';
import { BuiltinAction, CustomAction, errorText, runbookApi } from './runbookApi';

const inputClass =
  'w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500';

const EMPTY = { label: '', url: '', risky: true, description: '' };

export default function ActionsPanel({ onChanged }: { onChanged: () => void }) {
  const [builtin, setBuiltin] = useState<BuiltinAction[]>([]);
  const [custom, setCustom] = useState<CustomAction[]>([]);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState<number | 'new' | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function load() {
    try {
      const res = await runbookApi.actions();
      setBuiltin(res.builtin);
      setCustom(res.custom);
    } catch (e) {
      setError(errorText(e));
    }
  }

  useEffect(() => { load(); }, []);

  function startNew() {
    setForm(EMPTY);
    setEditingId('new');
    setError('');
  }

  function startEdit(a: CustomAction) {
    setForm({ label: a.label, url: a.url, risky: a.risky, description: a.description ?? '' });
    setEditingId(a.id);
    setError('');
  }

  async function save() {
    setSaving(true);
    setError('');
    const body = { ...form, description: form.description.trim() || null };
    try {
      if (editingId === 'new') await runbookApi.createAction(body);
      else if (typeof editingId === 'number') await runbookApi.updateAction(editingId, body);
      setEditingId(null);
      await load();
      onChanged();                       // runbooki są parsowane od nowa – mogą teraz rozpoznać akcję
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  async function remove(a: CustomAction) {
    setConfirmDelete(null);
    try {
      await runbookApi.removeAction(a.id);
      await load();
      onChanged();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <section className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-amber-400" />
          <div>
            <h2 className="font-bold text-white">Actions the app can run</h2>
            <p className="text-xs text-slate-400">
              Add your own action – no code needed. Runbooks can then use it, e.g. “Clear cache on pricing-engine”.
            </p>
          </div>
        </div>
        {editingId === null && (
          <button onClick={startNew}
            className="flex items-center gap-1 border border-slate-600 hover:border-amber-500 text-slate-200 px-3 py-1.5 rounded-lg text-sm shrink-0">
            <Plus className="w-4 h-4" />Add action
          </button>
        )}
      </div>

      {editingId !== null && (
        <div className="border border-amber-500/30 rounded-lg p-4 space-y-3 bg-slate-950/40">
          <div className="grid sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Name *</label>
              <input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })}
                placeholder="e.g. Clear cache" className={inputClass} />
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs font-semibold text-slate-300 mb-1">Address the app calls (POST) *</label>
              <input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })}
                placeholder="e.g. https://{{service}}/cache/clear" className={`${inputClass} font-mono text-xs`} />
            </div>
          </div>
          <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="What it does (optional)" className={inputClass} />
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={form.risky} onChange={(e) => setForm({ ...form, risky: e.target.checked })} />
            Risky – a team lead must approve it first
          </label>
          <p className="text-xs text-slate-500">
            Use <code className="text-slate-300">{'{{field}}'}</code> in the address for values from the event.
            In a runbook write the name (“Clear cache on pricing-engine”) or, in YAML,{' '}
            <code className="text-slate-300">action: {form.label ? form.label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') : 'clear_cache'}</code>.
          </p>
          <div className="flex items-center gap-3">
            <button onClick={save} disabled={saving || !form.label.trim() || !form.url.trim()}
              className="bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 font-bold px-4 py-2 rounded-lg text-sm">
              {saving ? 'Saving…' : editingId === 'new' ? 'Add action' : 'Save'}
            </button>
            <button onClick={() => setEditingId(null)} className="text-sm text-slate-400 hover:text-white">Cancel</button>
          </div>
        </div>
      )}

      {error && <p className="text-xs text-red-400">{error}</p>}

      <div className="space-y-2">
        {custom.length === 0 && editingId === null && (
          <p className="text-xs text-slate-500 italic">No team actions yet. Add one, e.g. “Clear cache” or “Fail over region”.</p>
        )}
        {custom.map((a) => (
          <div key={a.id} className="flex items-center gap-3 border border-slate-800 rounded-lg px-3 py-2 bg-slate-950/40">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-slate-200 text-sm">{a.label}</span>
                <code className="text-xs text-slate-500">{a.key}</code>
                <span className={`text-xs px-1.5 py-0.5 rounded border ${a.risky
                  ? 'border-amber-500/40 text-amber-300 bg-amber-500/10' : 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10'}`}>
                  {a.risky ? 'needs approval' : 'auto'}
                </span>
              </div>
              <p className="text-xs font-mono text-slate-400 truncate">POST {a.url}</p>
              {a.description && <p className="text-xs text-slate-500">{a.description}</p>}
            </div>
            {confirmDelete === a.id ? (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-slate-300">Delete?</span>
                <button onClick={() => remove(a)}
                  className="px-2 py-1 rounded bg-red-500/20 border border-red-500/50 text-red-300 hover:bg-red-500/30">Yes, delete</button>
                <button onClick={() => setConfirmDelete(null)} className="px-2 py-1 rounded text-slate-400 hover:text-white">No</button>
              </div>
            ) : (
              <div className="flex items-center gap-2 shrink-0">
                <button onClick={() => startEdit(a)} className="text-slate-400 hover:text-white" title="Edit"><Pencil className="w-4 h-4" /></button>
                <button onClick={() => setConfirmDelete(a.id)} className="text-slate-400 hover:text-red-400" title="Delete"><Trash2 className="w-4 h-4" /></button>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="text-xs text-slate-500">
        Built in:{' '}
        {builtin.map((b, i) => (
          <span key={b.key}>{i > 0 && ' · '}<span className="text-slate-300">{b.label}</span></span>
        ))}
      </div>
    </section>
  );
}
