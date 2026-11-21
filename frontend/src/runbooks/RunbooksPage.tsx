// OSOBA 4 – runbooki: wklej YAML / Markdown / tekst, zobacz kroki na żywo, zapisz, podepnij do reguły.
import { useEffect, useId, useMemo, useState } from 'react';
import { AlertTriangle, Check, ChevronDown, Info, Link2, Pencil, Plus, Save, Trash2, Unlink, X } from 'lucide-react';
import type { Runbook, RunbookStep } from '../shared/types';
import { MatchGroup, RuleRef, RunbookFormat, describeMatches, errorText, runbookApi } from './runbookApi';
import StepList from './StepList';
import EngineTester from './EngineTester';

const FORMATS: { value: RunbookFormat; label: string }[] = [
  { value: 'auto', label: 'Auto-detect' },
  { value: 'yaml', label: 'YAML' },
  { value: 'json', label: 'JSON' },
  { value: 'html', label: 'HTML (copied from a wiki)' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'text', label: 'Free text' },
  { value: 'link', label: 'Link' },
];

const EXAMPLE = `# Settlement workflow failed
1. Check settlement service health at https://settlement.internal/health
2. Retry workflow {{workflowId}} from step {{step}}
3. If the retry fails, call the Settlements on-call
4. Open a JIRA ticket with error {{error.code}}`;

const inputClass = 'field w-full px-3.5 py-2.5 text-sm';
const labelClass = 'block text-[13px] font-medium text-ink-muted mb-1.5';

// Short label for the format pill on a runbook card
const FORMAT_LABEL: Record<string, string> = {
  yaml: 'YAML', json: 'JSON', html: 'HTML', markdown: 'Markdown', text: 'Free text', link: 'Link',
};

type Editing = Runbook | 'new' | null;

export default function RunbooksPage() {
  const [runbooks, setRunbooks] = useState<Runbook[]>([]);
  const [rules, setRules] = useState<RuleRef[]>([]);
  const [loadError, setLoadError] = useState('');
  const [editing, setEditing] = useState<Editing>(null);
  const [notice, setNotice] = useState('');
  const [openIds, setOpenIds] = useState<Set<number>>(new Set());
  const allOpen = runbooks.length > 0 && runbooks.every((r) => openIds.has(r.id));

  function toggleOpen(id: number) {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

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

  async function handleDelete(rb: Runbook) {
    if (!confirm(`Delete runbook "${rb.name}"? Rules using it will be detached.`)) return;
    try {
      await runbookApi.remove(rb.id);
      if (editing !== null && editing !== 'new' && editing.id === rb.id) setEditing(null);
      await reload();
    } catch (e) {
      alert(errorText(e));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-semibold text-ink">Runbooks</h1>
          <p className="mt-1 text-sm text-ink-muted max-w-2xl">
            Paste a runbook in any format. Steps are extracted automatically and shown on every alert it is attached to.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {runbooks.length > 0 && (
            <button
              onClick={() => setOpenIds(allOpen ? new Set() : new Set(runbooks.map((r) => r.id)))}
              className="text-sm font-medium text-ink-muted hover:text-ink px-3 py-2 rounded-full hover:bg-white/5"
            >
              {allOpen ? 'Collapse all' : 'Expand all'}
            </button>
          )}
          {editing === null && (
            <button onClick={() => setEditing('new')} className="btn-primary flex items-center gap-2 px-4 h-10 text-sm">
              <Plus className="w-4 h-4" />New runbook
            </button>
          )}
        </div>
      </div>

      {loadError && (
        <p role="alert" className="text-sm text-signal-critical bg-signal-critical/10 rounded-xl px-4 py-2.5">
          Could not load runbooks: {loadError}
        </p>
      )}

      {notice && (
        <p role="status" className="flex items-center gap-2 text-sm text-signal-clear bg-signal-clear/10 rounded-xl px-4 py-2.5">
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
        {runbooks.map((rb) => (
          <RunbookCard
            key={rb.id}
            runbook={rb}
            attached={rules.filter((r) => r.runbook_id === rb.id)}
            editing={editing !== null && editing !== 'new' && editing.id === rb.id}
            open={openIds.has(rb.id)}
            onToggleOpen={() => toggleOpen(rb.id)}
            onEdit={() => setEditing(rb)}
            onDelete={() => handleDelete(rb)}
          />
        ))}
        {runbooks.length === 0 && !loadError && (
          <div className="surface p-10 text-center">
            <p className="text-ink font-medium">No runbooks yet</p>
            <p className="mt-1 text-sm text-ink-muted">Add one so responders see clear next steps on every alert.</p>
          </div>
        )}
      </div>

      <EngineTester />
    </div>
  );
}

// ---------------------------------------------------------------- karta

interface CardProps {
  runbook: Runbook;
  attached: RuleRef[];
  editing: boolean;
  open: boolean;
  onToggleOpen: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

function RunbookCard({ runbook: rb, attached, editing, open, onToggleOpen, onEdit, onDelete }: CardProps) {
  const stepsId = useId();
  const approvals = rb.steps.filter((s) => s.approval === 'required').length;
  const matches = (rb as Runbook & { matches?: MatchGroup | null }).matches;

  return (
    <article className={`surface ${editing ? 'ring-1 ring-gs-gold/50' : ''}`}>
      <div className="flex items-start gap-4 p-5">
        {/* Step count with one dot per step; amber dots need approval */}
        <div className="w-14 shrink-0 flex flex-col items-center pt-0.5" aria-hidden="true">
          <span className="text-2xl font-semibold leading-none tabular-nums text-ink">{rb.steps.length}</span>
          <span className="mt-1 text-[11px] text-ink-muted">{rb.steps.length === 1 ? 'step' : 'steps'}</span>
          <span className="mt-2 flex flex-wrap justify-center gap-[3px] max-w-[52px]">
            {rb.steps.slice(0, 12).map((s, i) => (
              <span key={i} className={`w-1.5 h-1.5 rounded-full ${s.approval === 'required' ? 'bg-signal-warning' : 'bg-white/25'}`} />
            ))}
          </span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-[17px] font-semibold leading-snug text-white">{rb.name}</h3>
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-white/5 text-ink-muted">
              {FORMAT_LABEL[rb.format] ?? rb.format}
            </span>
          </div>
          <p className="mt-1.5 text-[13px] text-ink-muted">
            {approvals > 0
              ? `${approvals} ${approvals === 1 ? 'step needs' : 'steps need'} approval before it runs.`
              : 'No step needs approval.'}
            {attached.length === 0 && ' Not attached to any rule yet.'}
          </p>
          {(attached.length > 0 || matches) && (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {attached.map((r) => (
                <span key={r.id} className="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full bg-white/5 text-ink">
                  <Link2 className="w-3 h-3 text-ink-muted" />{r.name}
                </span>
              ))}
              {matches && (
                <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-signal-info/10 text-signal-info">
                  For events where <code className="font-mono text-[11px]">{describeMatches(matches)}</code>
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <button type="button" onClick={onEdit} title="Edit runbook" aria-label={`Edit ${rb.name}`}
            className="w-9 h-9 rounded-full flex items-center justify-center text-ink-muted hover:text-ink hover:bg-white/5">
            <Pencil className="w-4 h-4" />
          </button>
          <button type="button" onClick={onDelete} title="Delete runbook" aria-label={`Delete ${rb.name}`}
            className="w-9 h-9 rounded-full flex items-center justify-center text-ink-muted hover:text-signal-critical hover:bg-signal-critical/10">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      <button
        type="button"
        onClick={onToggleOpen}
        aria-expanded={open}
        aria-controls={stepsId}
        className="w-full flex items-center justify-between px-5 py-2.5 border-t border-white/[0.06] text-[13px] font-medium text-ink-muted hover:text-ink hover:bg-white/[0.03] rounded-b-[20px]"
      >
        {open ? 'Hide steps' : `Show steps`}
        <ChevronDown className={`w-4 h-4 transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
      </button>

      <div id={stepsId} className="disclosure" data-open={open}>
        <div>
          <div className="px-5 pb-5" {...(open ? {} : ({ inert: '' } as Record<string, string>))}>
            <div className="surface-well p-4">
              <StepList steps={rb.steps} empty="This runbook has no steps yet." />
            </div>
          </div>
        </div>
      </div>
    </article>
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
  const [raw, setRaw] = useState(initial?.raw ?? EXAMPLE);
  const [preview, setPreview] = useState<RunbookStep[]>(initial?.steps ?? []);
  const [detected, setDetected] = useState('');
  const [parseError, setParseError] = useState('');
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const [ruleToAttach, setRuleToAttach] = useState('');
  const [warnings, setWarnings] = useState<string[]>([]);
  const [matches, setMatches] = useState<MatchGroup | null>(null);

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
        onSaved(await runbookApi.update(initial.id, name.trim(), raw, format), false);
        return;
      }
      const rb = await runbookApi.create(name.trim(), raw, format);
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
    <section className="surface ring-1 ring-gs-gold/30 p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">{initial ? `Edit ${initial.name}` : 'New runbook'}</h2>
        <button onClick={onClose} title="Close editor" aria-label="Close editor"
          className="w-9 h-9 rounded-full flex items-center justify-center text-ink-muted hover:text-ink hover:bg-white/5">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="grid sm:grid-cols-3 gap-3">
        <div className="sm:col-span-2">
          <label className={labelClass}>Name</label>
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
          <textarea value={raw} onChange={(e) => setRaw(e.target.value)} rows={14} spellCheck={false}
            className={`${inputClass} font-mono !text-[13px] leading-relaxed`} />
          <p className="text-xs text-ink-muted mt-1.5">
            Use <code className="font-mono text-ink">{'{{field}}'}</code> to insert values from the event, e.g.{' '}
            <code className="font-mono text-ink">{'{{workflowId}}'}</code>.
          </p>
        </div>
        <div>
          <label className={labelClass}>
            Steps preview {format === 'auto' && detected && !parseError && <span className="font-normal">, read as {FORMAT_LABEL[detected] ?? detected}</span>}
          </label>
          <div className="surface-well p-4 min-h-[200px]">
            {parseError
              ? <p className="text-sm text-signal-critical whitespace-pre-wrap">{parseError}</p>
              : <StepList steps={preview} empty="Start typing to see the steps." />}
          </div>
          {!parseError && warnings.length > 0 && (
            <div role="status" className="mt-3 text-xs text-signal-warning bg-signal-warning/10 rounded-xl px-3.5 py-2.5 space-y-1">
              {warnings.map((w) => (
                <p key={w} className="flex gap-2"><AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" /><span>{w}</span></p>
              ))}
            </div>
          )}
          {!parseError && matches && (
            <p className="mt-3 flex gap-2 text-xs text-signal-info bg-signal-info/10 rounded-xl px-3.5 py-2.5">
              <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>This runbook says which events it is for: <span className="font-mono">{describeMatches(matches)}</span>.
              Rules without their own runbook will use it for these events automatically.</span>
            </p>
          )}
        </div>
      </div>

      {!initial && (
        <div className="border-t border-white/[0.06] pt-5 space-y-1">
          <label htmlFor="new-runbook-rule" className={labelClass}>Attach to rule (optional)</label>
          <select id="new-runbook-rule" value={ruleToAttach} onChange={(e) => setRuleToAttach(e.target.value)}
            className={`${inputClass} sm:max-w-md`}>
            <option value="">Don't attach yet</option>
            {rules.map((r) => (
              <option key={r.id} value={r.id}>{r.name} ({r.team}){r.runbook_id ? ' – replaces its runbook' : ''}</option>
            ))}
          </select>
          <p className="text-xs text-ink-muted">Alerts from this rule will show these steps. You can change it later.</p>
        </div>
      )}

      {initial && (
        <div className="border-t border-white/[0.06] pt-5 space-y-2.5">
          <label className={labelClass}>Attached to rules</label>
          <div className="flex flex-wrap gap-2">
            {attached.length === 0 && <span className="text-sm text-ink-muted">None yet.</span>}
            {attached.map((r) => (
              <span key={r.id} className="inline-flex items-center gap-1.5 text-xs font-medium bg-white/5 text-ink pl-2.5 pr-1.5 py-1 rounded-full">
                {r.name}
                <button onClick={() => detach(r.id)} className="text-ink-muted hover:text-signal-critical" title="Detach" aria-label={`Detach from ${r.name}`}>
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
              className="flex items-center gap-1.5 bg-white/[0.07] hover:bg-white/10 disabled:opacity-40 text-ink font-medium px-4 rounded-full text-sm">
              <Link2 className="w-4 h-4" />Attach
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center gap-3 pt-1">
        <button onClick={save} disabled={saving || !!parseError}
          className="btn-primary flex items-center gap-2 px-5 h-10 text-sm disabled:opacity-50">
          <Save className="w-4 h-4" />{saving ? 'Saving…' : 'Save runbook'}
        </button>
        <button onClick={onClose} className="text-sm font-medium text-ink-muted hover:text-ink px-3 h-10 rounded-full hover:bg-white/5">Cancel</button>
        {saveError && <span role="alert" className="text-sm text-signal-critical">{saveError}</span>}
      </div>
    </section>
  );
}
