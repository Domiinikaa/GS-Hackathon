// Test silnika reguł "na sucho": wklej zdarzenie -> zobacz, które reguły pasują i jaki alert by powstał.
import { useState } from 'react';
import { Play } from 'lucide-react';
import { EngineResult, errorText, runbookApi } from './runbookApi';
import StepList from './StepList';

const SAMPLES: Record<string, unknown> = {
  'Settlement failed': {
    type: 'WORKFLOW_FAILED', workflowName: 'order-settlement', environment: 'prod',
    workflowId: 'WF-20931', step: 'book-cash', error: { code: 'TIMEOUT', message: 'Cash booking timed out after 30s' },
  },
  'Rejected trade': {
    meta: { schema: 'trade.rejected.v2', producer: 'trade-gateway' },
    payload: { tradeId: 'T-998877', desk: 'rates', notional: 25000000, currency: 'EUR', reason: 'LIMIT_BREACH' },
  },
  'Pricing warning': { service: 'pricing-engine-eu', level: 'WARN', instrument: 'EURUSD', message: 'Stale quote' },
  'Payments critical': {
    alertname: 'HighErrorRate', labels: { service: 'payments-api', severity: 'critical' },
    annotations: { summary: '5xx rate above 5% for 10 minutes' },
  },
};

const DOT: Record<string, string> = {
  red: 'bg-signal-critical', amber: 'bg-signal-warning', blue: 'bg-signal-info', green: 'bg-signal-clear', slate: 'bg-slate-500',
};

export default function EngineTester() {
  const [text, setText] = useState(JSON.stringify(SAMPLES['Settlement failed'], null, 2));
  const [result, setResult] = useState<EngineResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function run() {
    setError('');
    let event: unknown;
    try {
      event = JSON.parse(text);
    } catch (e) {
      setError(`Invalid JSON: ${(e as Error).message}`);
      return;
    }
    setBusy(true);
    try {
      setResult(await runbookApi.testEngine(event));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="glass-card glass-card--static p-6 space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Try the rule engine</h2>
          <p className="mt-0.5 text-sm text-ink-muted">Paste an event and see which rules would fire. Nothing is saved.</p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {Object.keys(SAMPLES).map((name) => (
            <button key={name} onClick={() => { setText(JSON.stringify(SAMPLES[name], null, 2)); setResult(null); }}
              className="text-xs font-medium bg-white/5 hover:bg-white/10 text-ink-muted hover:text-ink px-3 py-1.5 rounded-full">
              {name}
            </button>
          ))}
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="space-y-2">
          <textarea value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} rows={14}
            aria-label="Event JSON"
            className="field w-full px-3.5 py-3 font-mono text-[13px] leading-relaxed" />
          <button onClick={run} disabled={busy}
            className="btn-primary flex items-center gap-2 px-5 h-10 text-sm disabled:opacity-50">
            <Play className="w-4 h-4" />{busy ? 'Checking rules…' : 'Check rules'}
          </button>
          {error && <p role="alert" className="text-sm text-signal-critical">{error}</p>}
        </div>

        <div className="space-y-3">
          {!result && (
            <div className="surface-well p-6 h-full min-h-[200px] flex items-center justify-center text-center">
              <p className="text-sm text-ink-muted">Pick a sample or paste your own event,<br />then check which rules fire.</p>
            </div>
          )}
          {result && result.matched.length === 0 && (
            <div className="surface-well p-4 text-sm text-ink-muted">No rule matched. {result.checked.length} rules checked.</div>
          )}
          {result?.matched.map((m) => (
            <div key={m.rule_id} className="surface-well p-4 space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`w-2.5 h-2.5 rounded-full ${DOT[m.color] ?? 'bg-slate-500'}`} />
                <span className="font-semibold text-ink text-sm">{m.title}</span>
                <span className="text-xs font-medium capitalize text-ink-muted">{m.severity}</span>
              </div>
              {m.body && <p className="text-sm text-ink-muted">{m.body}</p>}
              <p className="text-xs text-ink-muted">
                Rule <span className="text-ink">{m.rule_id}</span>, sent to <span className="text-ink">{m.team}</span> by{' '}
                <span className="text-ink">{m.channels.join(', ') || 'no channel'}</span>. Grouped by{' '}
                <code className="font-mono text-[11px] text-ink">{m.dedup_key}</code>
              </p>
              <StepList steps={m.steps} empty="No runbook attached to this rule." />
            </div>
          ))}
          {result && result.not_matched.length > 0 && (
            <p className="text-xs text-ink-muted">Did not match: {result.not_matched.join(', ')}</p>
          )}
        </div>
      </div>
    </section>
  );
}
