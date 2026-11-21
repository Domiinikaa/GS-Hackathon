// Runbooki: wklej YAML / Markdown / tekst, zobacz kroki na żywo, zapisz, podepnij do reguły.
import { useEffect, useId, useMemo, useState } from 'react';
import { AlertTriangle, BookOpen, Check, ChevronRight, Info, Link2, Plus, Save, Unlink, X } from 'lucide-react';
import type { Runbook, RunbookStep, StepKind } from '../shared/types';
import { MatchGroup, RuleRef, RunbookFormat, describeMatches, errorText, runbookApi } from './runbookApi';
import StepList from './StepList';
import { EmptyState, PageHeader, Row, ghostButton } from '../shared/ui';
import EngineTester from './EngineTester';
import SimulatorPanel from './SimulatorPanel';
import ActionsPanel from './ActionsPanel';
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

// Przykłady w różnych formatach – pokazują, że runbook można wkleić w dowolnej postaci
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
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);  // id runbooka czekającego na "Yes"
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

  function duplicateRunbook(rb: Runbook) {
    const copy: Runbook = {
      ...rb,
      id: 0,
      name: `${rb.name}-copy`,
    };
    setEditing(copy);
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
      <PageHeader
        title="Runbooks"
        description="Paste a runbook in any format. Steps are pulled out automatically and shown on every alert it is attached to."
        actions={<>
          {runbooks.length > 0 && (
            <button onClick={() => setOpenIds(allOpen ? new Set() : new Set(runbooks.map((r) => r.id)))} className={ghostButton}>
              {allOpen ? 'Collapse all' : 'Expand all'}
            </button>
          )}
          {editing === null && (
            <button onClick={() => setEditing('new')} className="btn-primary flex items-center gap-1.5 px-4 h-9 text-[15px]">
              <Plus className="w-4 h-4" />New runbook
            </button>
          )}
        </>}
      />

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

      <div className="grid gap-5 lg:grid-cols-2 items-start">
        {runbooks.map((rb) => (
          <RunbookCard
            key={rb.id}
            runbook={rb}
            attached={rules.filter((r) => r.runbook_id === rb.id)}
            editing={editing !== null && editing !== 'new' && editing.id === rb.id}
            open={openIds.has(rb.id)}
            onToggleOpen={() => toggleOpen(rb.id)}
            onEdit={() => setEditing(rb)}
            onDuplicate={() => duplicateRunbook(rb)}
            confirming={confirmDelete === rb.id}
            onAskDelete={() => setConfirmDelete(rb.id)}
            onCancelDelete={() => setConfirmDelete(null)}
            onDelete={() => handleDelete(rb)}
          />
        ))}
        {runbooks.length === 0 && !loadError && (
          <div className="lg:col-span-2"><EmptyState icon={BookOpen} title="No runbooks yet"
            text="Add one so responders see clear next steps on every alert." /></div>
        )}
      </div>

      <ActionsPanel onChanged={reload} />

      <SimulatorPanel />

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
  onDuplicate: () => void;
  confirming: boolean;        // waiting for "Yes, delete"
  onAskDelete: () => void;
  onCancelDelete: () => void;
  onDelete: () => void;
}

function RunbookCard({ runbook: rb, attached, editing, open, onToggleOpen, onEdit, onDuplicate, confirming, onAskDelete, onCancelDelete, onDelete }: CardProps) {
  const stepsId = useId();
  const approvals = rb.steps.filter((s) => s.approval === 'required').length;
  const matches = (rb as Runbook & { matches?: MatchGroup | null }).matches;

  return (
    <article className={`ios-group ${editing ? 'ring-2 ring-ios-blue' : ''}`}>
      <div className="ios-row py-3.5">
        <div className="flex-1 min-w-0">
          <h3 className="text-[17px] font-semibold text-white leading-snug">{rb.name}</h3>
          <p className="text-[13px] text-ink-muted">{FORMAT_LABEL[rb.format] ?? rb.format}</p>
        </div>
      </div>
      <Row label="Steps" value={<span className="tabular-nums">{rb.steps.length}</span>} />
      <Row label="Need approval" value={<span className={approvals > 0 ? 'text-ios-orange tabular-nums' : 'tabular-nums'}>{approvals}</span>} />
      <Row label="Used by" value={attached.length ? attached.map((r) => r.name).join(', ') : 'No rule yet'} />
      {matches && <Row label="Applies to" value={<code className="font-mono text-[13px]">{describeMatches(matches)}</code>} />}

      <button type="button" onClick={onToggleOpen} aria-expanded={open} aria-controls={stepsId}
        className="ios-row ios-row--tap w-full text-left">
        <span className="flex-1 text-[15px] text-white">{open ? 'Hide steps' : 'Show steps'}</span>
        <ChevronRight className={`w-4 h-4 text-ink-faint transition-transform duration-300 ${open ? 'rotate-90' : ''}`} aria-hidden="true" />
      </button>
      <div id={stepsId} className="disclosure ios-divided" data-open={open}>
        <div {...(open ? {} : ({ inert: '' } as Record<string, string>))}>
          <div className="bg-black/25 px-4 py-4">
            <StepList steps={rb.steps} empty="This runbook has no steps yet." />
          </div>
        </div>
      </div>

      {confirming ? (
        <div className="ios-row flex-wrap justify-between ios-divided">
          <span className="text-[15px] text-white">
            Delete?{attached.length > 0 && ` ${attached.length} rule${attached.length > 1 ? 's' : ''} will be detached.`}
          </span>
          <span className="flex items-center gap-4">
            <button type="button" onClick={onCancelDelete} className="text-[15px] text-ios-blue hover:opacity-70">No</button>
            <button type="button" onClick={onDelete} className="text-[15px] font-semibold text-ios-red hover:opacity-70">Yes, delete</button>
          </span>
        </div>
      ) : (
        <div className="ios-row justify-between ios-divided">
          <div className="flex items-center gap-4">
            <button type="button" onClick={onEdit} className="text-[15px] text-ios-blue hover:opacity-70">Edit runbook</button>
            <button type="button" onClick={onDuplicate} className="text-[15px] text-amber-400 hover:opacity-70">Duplicate</button>
          </div>
          <button type="button" onClick={onAskDelete} className="text-[15px] text-ios-red hover:opacity-70">Delete</button>
        </div>
      )}
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
      if (initial && initial.id > 0) {
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
    <section className="glass-card glass-card--static ring-1 ring-gs-gold/30 p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">
          {initial && initial.id > 0 ? `Edit ${initial.name}` : initial ? `Duplicate "${name}"` : 'New runbook'}
        </h2>
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
          <textarea value={raw} onChange={(e) => setRaw(e.target.value)} rows={14} spellCheck={false} placeholder={PLACEHOLDER}
            className={`${inputClass} font-mono !text-[13px] leading-relaxed`} />
          {!raw.trim() && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-xs text-ink-muted">Start from an example:</span>
              {EXAMPLES.map((ex) => (
                <button key={ex.label} type="button" title={ex.hint} onClick={() => { setFormat('auto'); setRaw(ex.raw); }}
                  className="text-xs px-2.5 py-1 rounded-full bg-ios-fill text-ios-blue hover:bg-white/[0.16] transition-colors">
                  {ex.label}
                </button>
              ))}
            </div>
          )}
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
              ? <p className="text-sm text-ios-red whitespace-pre-wrap">{parseError}</p>
              : <StepList steps={steps} empty="Start typing to see the steps."
                  onKindChange={(i, kind) => setKindByText((k) => ({ ...k, [preview[i].text]: kind }))} />}
          </div>
          {!parseError && steps.length > 0 && (
            <p className="text-xs text-ink-muted mt-2 leading-relaxed">
              <span className="text-ios-green">Auto</span>: the app does it.{' '}
              <span className="text-ios-orange">Needs approval</span>: the app does it after a team lead approves.{' '}
              <span className="text-ink">Manual</span>: a person does it. Change it with the label on each step.
            </p>
          )}
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
