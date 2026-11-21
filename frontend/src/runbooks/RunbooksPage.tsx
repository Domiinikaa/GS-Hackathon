// OSOBA 4 – runbooki: wklej YAML / Markdown / tekst, zobacz kroki na żywo, zapisz, podepnij do reguły.
import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, BookOpen, Check, Link2, Plus, Save, Trash2, Unlink, X } from 'lucide-react';
import type { Runbook, RunbookStep, StepKind } from '../shared/types';
import { MatchGroup, RuleRef, RunbookFormat, describeMatches, errorText, runbookApi } from './runbookApi';
import StepList from './StepList';
import EngineTester from './EngineTester';
import SimulatorPanel from './SimulatorPanel';
import { withKind } from './stepKind';

const FORMATS: { value: RunbookFormat; label: string }[] = [
  { value: 'auto', label: 'Auto-detect' },
  { value: 'yaml', label: 'YAML' },
  { value: 'json', label: 'JSON' },
  { value: 'html', label: 'HTML (copied from a wiki)' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'text', label: 'Free text' },
  { value: 'link', label: 'Link' },
];

// Przykłady w różnych formatach – pokazują, że runbook można wkleić w dowolnej postaci (kartka: Appendix B)
const EXAMPLES: { label: string; hint: string; raw: string }[] = [
  {
    label: 'Numbered list',
    hint: 'Markdown or a checklist copied from a doc',
    raw: `# Settlement workflow failed
1. Check settlement service health at https://settlement.internal/health
2. Retry workflow {{workflowId}} from step {{step}}
3. If the retry fails, call the Settlements on-call
4. Open a JIRA ticket with error {{error.code}}`,
  },
  {
    label: 'YAML',
    hint: 'Structured steps with actions and approvals',
    raw: `runbook: settlement-timeout
matches:
  type: WORKFLOW_FAILED
  "error.code": TIMEOUT
steps:
  - check: "Is counterparty-service healthy?"
    action: http_get
    url: "http://counterparty-service/health"
  - action: retry_workflow
    workflowId: "{{workflowId}}"
    approval: none
  - if: "retry fails twice"
    action: escalate
    team: counterparty-support
    approval: required`,
  },
  {
    label: 'Free text',
    hint: 'A paragraph from a wiki or a chat message',
    raw: `When pricing latency goes over a second, it's usually the cache. Restart the pricing-engine instance named in the alert, wait 2 minutes, and if latency is still high, call the pricing on-call person.`,
  },
  {
    label: 'Wiki link',
    hint: 'Just a link to Confluence or a wiki page',
    raw: 'https://wiki.example.com/runbooks/payments-high-error-rate',
  },
];

const PLACEHOLDER = `Paste a runbook in any format, for example:

  1. Check service health at http://...    <- numbered list
  steps:  - action: retry_workflow         <- YAML
  When X happens, restart Y, then ...      <- free text
  https://wiki.example.com/runbook         <- link

No idea where to start? Click one of the example buttons under this box.`;

const inputClass =
  'w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500';
const labelClass = 'block text-xs font-semibold text-slate-300 mb-1';

type Editing = Runbook | 'new' | null;

export default function RunbooksPage() {
  const [runbooks, setRunbooks] = useState<Runbook[]>([]);
  const [rules, setRules] = useState<RuleRef[]>([]);
  const [loadError, setLoadError] = useState('');
  const [editing, setEditing] = useState<Editing>(null);
  const [notice, setNotice] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);  // id runbooka czekającego na "Yes"

  // krótki komunikat po akcji (np. "Saved"), znika sam po 4 s
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(''), 4000);
    return () => clearTimeout(t);
  }, [notice]);

  async function reload() {
    try {
      const [rb, rl] = await Promise.all([runbookApi.list(), runbookApi.rules()]);
      setRunbooks(rb);
      setRules(rl);
      setLoadError('');
    } catch (e) {
      setLoadError(errorText(e));
    }
  }

  useEffect(() => { reload(); }, []);

  async function handleSaved(rb: Runbook, isNew: boolean, attachedTo?: string, attachError?: string) {
    await reload();
    setEditing(null);
    if (attachError) {
      setNotice(`Saved "${rb.name}", but could not attach it to the rule: ${attachError}. Click its card to try again.`);
    } else if (attachedTo) {
      setNotice(`Saved "${rb.name}" and attached it to "${attachedTo}". New alerts from this rule will show these steps.`);
    } else if (isNew) {
      setNotice(`Saved "${rb.name}". It is not attached to any rule yet: click its card to attach one.`);
    } else {
      setNotice(`Saved "${rb.name}".`);
    }
  }

  async function handleRulesChanged(message: string) {
    await reload();
    setNotice(message);
  }

  // potwierdzenie na karcie, nie window.confirm() – niektóre przeglądarki (np. wbudowane) go nie pokazują
  async function handleDelete(rb: Runbook) {
    setConfirmDelete(null);
    try {
      await runbookApi.remove(rb.id);
      if (editing !== null && editing !== 'new' && editing.id === rb.id) setEditing(null);
      await reload();
      setNotice(`Deleted "${rb.name}".`);
    } catch (e) {
      setLoadError(`Could not delete "${rb.name}": ${errorText(e)}`);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Runbooks</h1>
          <p className="text-sm text-slate-400">
            Paste a runbook in any format. Steps are extracted automatically and attached to alerts.
          </p>
        </div>
        {editing === null && (
          <button onClick={() => setEditing('new')}
            className="flex items-center space-x-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold px-4 py-2 rounded-lg text-sm">
            <Plus className="w-4 h-4" /><span>New runbook</span>
          </button>
        )}
      </div>

      {loadError && (
        <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          Could not load runbooks: {loadError}
        </p>
      )}

      {notice && (
        <p role="status" className="flex items-center gap-2 text-sm text-emerald-300 bg-emerald-500/10 border border-emerald-500/40 rounded-lg px-3 py-2">
          <Check className="w-4 h-4 shrink-0" />{notice}
        </p>
      )}

      {editing !== null && (
        <RunbookEditor
          key={editing === 'new' ? 'new' : editing.id}
          initial={editing === 'new' ? undefined : editing}
          rules={rules}
          onSaved={handleSaved}
          onRulesChanged={handleRulesChanged}
          onClose={() => setEditing(null)}
        />
      )}

      <div className="space-y-3">
        {runbooks.map((rb) => {
          const attached = rules.filter((r) => r.runbook_id === rb.id);
          const active = editing !== null && editing !== 'new' && editing.id === rb.id;
          return (
            <div key={rb.id} onClick={() => setEditing(rb)}
              className={`bg-slate-900 border rounded-xl p-5 flex gap-4 cursor-pointer hover:border-slate-600 ${
                active ? 'border-amber-500/60' : 'border-slate-800'}`}>
              <BookOpen className="w-5 h-5 text-slate-400 mt-0.5 shrink-0" />
              <div className="flex-1 space-y-2 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="font-bold text-white">{rb.name}</h3>
                  <span className="text-xs uppercase text-slate-500">{rb.format}</span>
                  <span className="text-xs text-slate-400 bg-slate-800 px-2 py-0.5 rounded">{rb.steps.length} steps</span>
                </div>
                <p className="text-sm text-slate-400 truncate">{rb.steps.map((s) => s.text).join(' → ')}</p>
                <div className="flex gap-2 flex-wrap">
                  {(rb as Runbook & { matches?: MatchGroup | null }).matches && (
                    <span className="text-xs bg-sky-500/10 border border-sky-500/30 text-sky-300 px-2 py-0.5 rounded font-mono">
                      for events: {describeMatches((rb as Runbook & { matches?: MatchGroup | null }).matches)}
                    </span>
                  )}
                  {attached.length === 0
                    ? <span className="text-xs text-slate-500">Not attached to any rule</span>
                    : attached.map((r) => (
                      <span key={r.id} className="inline-flex items-center gap-1 text-xs bg-slate-800 border border-slate-700 text-slate-300 px-2 py-0.5 rounded">
                        <Link2 className="w-3 h-3" />{r.name}
                      </span>
                    ))}
                </div>
              </div>
              {confirmDelete === rb.id ? (
                <div onClick={(e) => e.stopPropagation()} className="self-start flex items-center gap-2 text-xs cursor-default">
                  <span className="text-slate-300">
                    Delete?{attached.length > 0 && ` ${attached.length} rule${attached.length > 1 ? 's' : ''} will be detached.`}
                  </span>
                  <button onClick={() => handleDelete(rb)}
                    className="px-2 py-1 rounded bg-red-500/20 border border-red-500/50 text-red-300 hover:bg-red-500/30">Yes, delete</button>
                  <button onClick={() => setConfirmDelete(null)} className="px-2 py-1 rounded text-slate-400 hover:text-white">No</button>
                </div>
              ) : (
                <button onClick={(e) => { e.stopPropagation(); setConfirmDelete(rb.id); }}
                  className="text-slate-400 hover:text-red-400 self-start" title="Delete">
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          );
        })}
        {runbooks.length === 0 && !loadError && (
          <p className="text-center text-slate-500 py-8">No runbooks yet. Create the first one!</p>
        )}
      </div>

      <SimulatorPanel />

      <EngineTester />
    </div>
  );
}

// ---------------------------------------------------------------- edytor

interface EditorProps {
  initial?: Runbook;
  rules: RuleRef[];
  onSaved: (rb: Runbook, isNew: boolean, attachedTo?: string, attachError?: string) => void;
  onRulesChanged: (message: string) => void;
  onClose: () => void;
}

function RunbookEditor({ initial, rules, onSaved, onRulesChanged, onClose }: EditorProps) {
  const [name, setName] = useState(initial?.name ?? '');
  const [format, setFormat] = useState<RunbookFormat>(initial ? (initial.format as RunbookFormat) : 'auto');
  const [raw, setRaw] = useState(initial?.raw ?? '');
  const [preview, setPreview] = useState<RunbookStep[]>(initial?.steps ?? []);
  const [detected, setDetected] = useState('');
  const [parseError, setParseError] = useState('');
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const [ruleToAttach, setRuleToAttach] = useState('');
  const [warnings, setWarnings] = useState<string[]>([]);
  const [matches, setMatches] = useState<MatchGroup | null>(null);
  // ręcznie wybrany rodzaj kroku, po tekście kroku (przetrwa edycję innych linijek)
  const [kindByText, setKindByText] = useState<Record<string, StepKind>>(() =>
    Object.fromEntries((initial?.steps ?? []).filter((s) => s.kind).map((s) => [s.text, s.kind as StepKind])));
  const steps = useMemo(
    () => preview.map((s) => (kindByText[s.text] ? withKind(s, kindByText[s.text]) : s)),
    [preview, kindByText],
  );
  const kinds = () => preview.map((s) => kindByText[s.text] ?? null);

  // podgląd na żywo: pytamy backend 300 ms po ostatnim naciśnięciu klawisza
  useEffect(() => {
    if (!raw.trim()) { setPreview([]); setDetected(''); setParseError(''); setWarnings([]); setMatches(null); return; }
    const timer = setTimeout(async () => {
      try {
        const res = await runbookApi.parse(raw, format);
        setPreview(res.steps);
        setDetected(res.format);
        setWarnings(res.warnings ?? []);
        setMatches(res.matches ?? null);
        setParseError('');
        // nowy runbook bez nazwy: weź nazwę z treści ("runbook: settlement-timeout")
        if (!initial && res.name) setName((n) => (n.trim() ? n : res.name ?? n));
      } catch (e) {
        setDetected('');  // nie pokazuj formatu z poprzedniego, udanego odczytu
        setWarnings([]);
        setMatches(null);
        setParseError(errorText(e));
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [raw, format]);

  const attached = useMemo(() => rules.filter((r) => initial && r.runbook_id === initial.id), [rules, initial]);
  const attachable = rules.filter((r) => !initial || r.runbook_id !== initial.id);

  async function save() {
    if (!name.trim()) { setSaveError('Name is required.'); return; }
    setSaving(true);
    setSaveError('');
    try {
      if (initial) {
        onSaved(await runbookApi.update(initial.id, name.trim(), raw, format, kinds()), false);
        return;
      }
      const rb = await runbookApi.create(name.trim(), raw, format, kinds());
      // nowy runbook: od razu podpinamy do wybranej reguły (jeśli wybrano)
      if (!ruleToAttach) { onSaved(rb, true); return; }
      const rule = rules.find((r) => r.id === ruleToAttach);
      try {
        await runbookApi.attach(rb.id, ruleToAttach);
        onSaved(rb, true, rule?.name ?? ruleToAttach);
      } catch (e) {
        onSaved(rb, true, undefined, errorText(e));
      }
    } catch (e) {
      setSaveError(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  async function attach() {
    if (!initial || !ruleToAttach) return;
    try {
      await runbookApi.attach(initial.id, ruleToAttach);
      const rule = rules.find((r) => r.id === ruleToAttach);
      setRuleToAttach('');
      onRulesChanged(`Attached to "${rule?.name ?? ruleToAttach}". New alerts from this rule will show these steps.`);
    } catch (e) {
      setSaveError(errorText(e));
    }
  }

  async function detach(ruleId: string) {
    if (!initial) return;
    try {
      await runbookApi.detach(initial.id, ruleId);
      onRulesChanged('Detached from the rule.');
    } catch (e) {
      setSaveError(errorText(e));
    }
  }

  return (
    <section className="bg-slate-900 border border-amber-500/30 rounded-xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-bold text-white">{initial ? `Edit runbook #${initial.id}` : 'New runbook'}</h2>
        <button onClick={onClose} className="text-slate-400 hover:text-white" title="Close"><X className="w-4 h-4" /></button>
      </div>

      <div className="grid sm:grid-cols-3 gap-3">
        <div className="sm:col-span-2">
          <label className={labelClass}>Name *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. settlement-timeout" className={inputClass} />
        </div>
        <div>
          <label className={labelClass}>Format</label>
          <select value={format} onChange={(e) => setFormat(e.target.value as RunbookFormat)} className={inputClass}>
            {FORMATS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Runbook content</label>
          <textarea value={raw} onChange={(e) => setRaw(e.target.value)} rows={14} spellCheck={false} placeholder={PLACEHOLDER}
            className={`${inputClass} font-mono text-xs`} />
          {!raw.trim() && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-400">Start from an example:</span>
              {EXAMPLES.map((ex) => (
                <button key={ex.label} type="button" title={ex.hint} onClick={() => { setFormat('auto'); setRaw(ex.raw); }}
                  className="text-xs px-2.5 py-1 rounded-full border border-slate-700 text-slate-300 hover:border-amber-500 hover:text-amber-300">
                  {ex.label}
                </button>
              ))}
            </div>
          )}
          <p className="text-xs text-slate-500 mt-1">
            Use <code className="text-slate-300">{'{{field}}'}</code> to insert values from the event, e.g.{' '}
            <code className="text-slate-300">{'{{workflowId}}'}</code>.
          </p>
        </div>
        <div>
          <label className={labelClass}>
            Extracted steps {format === 'auto' && detected && !parseError && <span className="text-slate-500 font-normal">(detected: {detected})</span>}
          </label>
          {parseError
            ? <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2 whitespace-pre-wrap">{parseError}</p>
            : <StepList steps={steps} empty="Start typing to see steps."
                onKindChange={(i, kind) => setKindByText((k) => ({ ...k, [preview[i].text]: kind }))} />}
          {!parseError && steps.length > 0 && (
            <p className="text-xs text-slate-500 mt-2">
              <span className="text-emerald-300">auto</span>: the app does it ·{' '}
              <span className="text-amber-300">needs approval</span>: the app does it after a team lead approves ·{' '}
              <span className="text-slate-300">manual</span>: a person does it. Change it with the label on each step.
            </p>
          )}
          {!parseError && warnings.length > 0 && (
            <div role="status" className="mt-3 text-xs text-amber-300 bg-amber-500/10 border border-amber-500/40 rounded-lg px-3 py-2 space-y-1">
              {warnings.map((w) => (
                <p key={w} className="flex gap-2"><AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" /><span>{w}</span></p>
              ))}
            </div>
          )}
          {!parseError && matches && (
            <p className="mt-3 text-xs text-sky-300 bg-sky-500/10 border border-sky-500/30 rounded-lg px-3 py-2">
              This runbook says which events it is for: <span className="font-mono">{describeMatches(matches)}</span>.
              Rules without their own runbook will use it for these events automatically.
            </p>
          )}
        </div>
      </div>

      {!initial && (
        <div className="border-t border-slate-800 pt-4 space-y-1">
          <label htmlFor="new-runbook-rule" className={labelClass}>Attach to rule (optional)</label>
          <select id="new-runbook-rule" value={ruleToAttach} onChange={(e) => setRuleToAttach(e.target.value)}
            className={`${inputClass} sm:max-w-md`}>
            <option value="">Don't attach yet</option>
            {rules.map((r) => (
              <option key={r.id} value={r.id}>{r.name} ({r.team}){r.runbook_id ? ' – replaces its runbook' : ''}</option>
            ))}
          </select>
          <p className="text-xs text-slate-500">Alerts from this rule will show these steps. You can change it later.</p>
        </div>
      )}

      {initial && (
        <div className="border-t border-slate-800 pt-4 space-y-2">
          <label className={labelClass}>Attached to rules</label>
          <div className="flex flex-wrap gap-2">
            {attached.length === 0 && <span className="text-xs text-slate-500">None yet.</span>}
            {attached.map((r) => (
              <span key={r.id} className="inline-flex items-center gap-1 text-xs bg-slate-800 border border-slate-700 text-slate-300 px-2 py-1 rounded">
                {r.name}
                <button onClick={() => detach(r.id)} className="text-slate-500 hover:text-red-400" title="Detach">
                  <Unlink className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <select value={ruleToAttach} onChange={(e) => setRuleToAttach(e.target.value)} className={`${inputClass} sm:max-w-sm`}>
              <option value="">Choose a rule…</option>
              {attachable.map((r) => (
                <option key={r.id} value={r.id}>{r.name} ({r.team}){r.runbook_id ? ' – replaces its runbook' : ''}</option>
              ))}
            </select>
            <button onClick={attach} disabled={!ruleToAttach}
              className="flex items-center gap-1 border border-slate-600 hover:border-amber-500 disabled:opacity-40 text-slate-200 px-3 py-2 rounded-lg text-sm">
              <Link2 className="w-4 h-4" />Attach
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center gap-3">
        <button onClick={save} disabled={saving || !!parseError}
          className="flex items-center gap-2 bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 font-bold px-4 py-2 rounded-lg text-sm">
          <Save className="w-4 h-4" />{saving ? 'Saving…' : 'Save runbook'}
        </button>
        <button onClick={onClose} className="text-sm text-slate-400 hover:text-white">Cancel</button>
        {saveError && <span className="text-xs text-red-400">{saveError}</span>}
      </div>
    </section>
  );
}
