// Test silnika reguł "na sucho": wklej zdarzenie -> zobacz, które reguły pasują i jaki alert by powstał.
import { useState } from 'react';
import { FlaskConical, Play } from 'lucide-react';
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
  red: 'bg-red-500', amber: 'bg-amber-500', blue: 'bg-blue-500', green: 'bg-emerald-500', slate: 'bg-slate-500',
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
    <section className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <FlaskConical className="w-5 h-5 text-amber-400" />
          <div>
            <h2 className="font-bold text-white">Rule engine playground</h2>
            <p className="text-xs text-slate-400">Paste an event and see which rules fire. Nothing is saved.</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-1">
          {Object.keys(SAMPLES).map((name) => (
            <button key={name} onClick={() => { setText(JSON.stringify(SAMPLES[name], null, 2)); setResult(null); }}
              className="text-xs border border-slate-700 text-slate-300 hover:border-amber-500 hover:text-white px-2 py-1 rounded">
              {name}
            </button>
          ))}
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <div className="space-y-2">
          <textarea value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} rows={14}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-amber-500" />
          <button onClick={run} disabled={busy}
            className="flex items-center gap-2 bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-slate-950 font-bold px-4 py-2 rounded-lg text-sm">
            <Play className="w-4 h-4" />{busy ? 'Evaluating…' : 'Evaluate'}
          </button>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>

        <div className="space-y-3">
          {!result && <p className="text-sm text-slate-500 italic">Results appear here.</p>}
          {result && result.matched.length === 0 && (
            <p className="text-sm text-slate-400">No rule matched ({result.checked.length} checked).</p>
          )}
          {result?.matched.map((m) => (
            <div key={m.rule_id} className="border border-slate-700 rounded-lg p-3 space-y-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`w-2.5 h-2.5 rounded-full ${DOT[m.color] ?? 'bg-slate-500'}`} />
                <span className="font-semibold text-white text-sm">{m.title}</span>
                <span className="text-xs uppercase text-slate-500">{m.severity}</span>
              </div>
              {m.body && <p className="text-sm text-slate-300">{m.body}</p>}
              <div className="flex flex-wrap gap-2 text-xs">
                <span className="bg-slate-800 text-slate-300 px-2 py-0.5 rounded">rule: {m.rule_id}</span>
                <span className="bg-slate-800 text-slate-300 px-2 py-0.5 rounded">team: {m.team}</span>
                <span className="bg-slate-800 text-slate-300 px-2 py-0.5 rounded">→ {m.channels.join(', ') || 'no channels'}</span>
                <span className="font-mono text-slate-500">dedup: {m.dedup_key}</span>
              </div>
              <StepList steps={m.steps} empty="No runbook attached to this rule." />
            </div>
          ))}
          {result && result.not_matched.length > 0 && (
            <p className="text-xs text-slate-500">Not matched: {result.not_matched.join(', ')}</p>
          )}
        </div>
      </div>
    </section>
  );
}
