import { useState } from 'react';
import { Play, X, CheckCircle2, AlertTriangle, Sparkles } from 'lucide-react';
import { api } from '../shared/api';
import type { Source } from '../shared/types';
import type { SimulateResult, SimulatorPreset } from './sourceTypes';

interface SimulateModalProps {
  source: Source;
  presets: SimulatorPreset[];
  onClose: () => void;
  onSimulated: () => void;
}

export default function SimulateModal({
  source,
  presets,
  onClose,
  onSimulated,
}: SimulateModalProps) {
  const defaultPreset =
    typeof source.config?.sim_preset === 'string' && source.config.sim_preset
      ? source.config.sim_preset
      : presets[0]?.id || 'workflow_failure';

  const [mode, setMode] = useState<'preset' | 'custom'>('preset');
  const [preset, setPreset] = useState<string>(defaultPreset);
  const [count, setCount] = useState<number>(1);
  const [customPayload, setCustomPayload] = useState<string>(() => {
    if (source.sample_event) {
      return JSON.stringify(source.sample_event, null, 2);
    }
    const found = presets.find((p) => p.id === defaultPreset);
    if (!found) return '{}';
    return typeof found.sample === 'string' ? found.sample : JSON.stringify(found.sample, null, 2);
  });
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SimulateResult | null>(null);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const body: Record<string, unknown> = { count };
      if (mode === 'preset') {
        body.preset = preset;
      } else {
        body.custom_payload = customPayload;
      }
      const res = await api<SimulateResult>(`/sources/${source.id}/simulate`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
      setResult(res);
      onSimulated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Simulation failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-amber-400" />
              Simulate Events — <span className="text-amber-400">{source.name}</span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Inject synthetic events through the <code className="text-slate-200">{source.kind}</code> ingestion & parser pipeline.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
          <div className="flex items-center gap-2 bg-slate-950 p-1 rounded-lg border border-slate-800 w-fit">
            <button
              type="button"
              onClick={() => setMode('preset')}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                mode === 'preset' ? 'bg-amber-500 text-slate-950 font-semibold' : 'text-slate-400 hover:text-white'
              }`}
            >
              Scenario Preset
            </button>
            <button
              type="button"
              onClick={() => setMode('custom')}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                mode === 'custom' ? 'bg-amber-500 text-slate-950 font-semibold' : 'text-slate-400 hover:text-white'
              }`}
            >
              Custom JSON / Raw Log
            </button>
          </div>

          {mode === 'preset' ? (
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Event Scenario
              </label>
              <select
                value={preset}
                onChange={(e) => setPreset(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
              >
                {presets.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label} — {p.description}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Custom Payload (JSON, NDJSON, or raw log line)
              </label>
              <textarea
                rows={7}
                value={customPayload}
                onChange={(e) => setCustomPayload(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-xs font-mono text-emerald-300 focus:outline-none focus:border-amber-500"
              />
            </div>
          )}

          <div className="flex items-center gap-4">
            <div className="w-40">
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Event Count (1–50)
              </label>
              <input
                type="number"
                min={1}
                max={50}
                value={count}
                onChange={(e) => setCount(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
              />
            </div>
            <p className="text-xs text-slate-400 pt-5">
              Each event is parsed using this source&apos;s parser, envelope unwrapping, and field aliases, then stored in <code className="text-slate-300">events</code>.
            </p>
          </div>

          {error && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {result && (
            <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 space-y-2">
              <div className="flex items-center gap-2 text-emerald-300 text-sm font-semibold">
                <CheckCircle2 className="w-4 h-4" />
                Ingested {result.simulated_count} event{result.simulated_count === 1 ? '' : 's'} ({result.alerts.length} alert{result.alerts.length === 1 ? '' : 's'} triggered)
              </div>
              {result.last_parsed && (
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-slate-400 mb-1">
                    Last Parsed Record
                  </div>
                  <pre className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-[11px] font-mono text-slate-200 overflow-x-auto max-h-48">
                    {JSON.stringify(result.last_parsed, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-slate-800 flex items-center justify-end gap-2 bg-slate-900/60">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-slate-300 hover:text-white hover:bg-slate-800 transition"
          >
            Close
          </button>
          <button
            type="button"
            disabled={running}
            onClick={handleRun}
            className="px-4 py-2 rounded-lg text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-slate-950 flex items-center gap-1.5 disabled:opacity-50 transition"
          >
            <Play className="w-4 h-4" />
            {running ? 'Simulating...' : `Send ${count} Simulated Event${count === 1 ? '' : 's'}`}
          </button>
        </div>
      </div>
    </div>
  );
}
