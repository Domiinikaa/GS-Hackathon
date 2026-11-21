// OSOBA 4 – symulator systemów docelowych: przełączniki "działa / nie działa" + dziennik tego,
// co aplikacja zrobiła w udawanym świecie (sprawdzenie zdrowia, ponowienie, restart, ticket, eskalacja).
import { useEffect, useState } from 'react';
import { Server } from 'lucide-react';
import { SimCall, SimService, errorText, runbookApi } from './runbookApi';
import { parseUtc } from '../alerts/AlertCard';

function time(iso: string): string {
  return parseUtc(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export default function SimulatorPanel() {
  const [services, setServices] = useState<SimService[]>([]);
  const [calls, setCalls] = useState<SimCall[]>([]);
  const [error, setError] = useState('');

  async function load() {
    try {
      const [s, c] = await Promise.all([runbookApi.simServices(), runbookApi.simCalls(15)]);
      setServices(s);
      setCalls(c);
      setError('');
    } catch (e) {
      setError(errorText(e));
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);   // odświeżanie, żeby było widać, co robi aplikacja
    return () => clearInterval(t);
  }, []);

  async function toggle(svc: SimService, field: 'healthy' | 'workflows_ok') {
    try {
      await runbookApi.setSimService(svc.name, { [field]: !svc[field] });
      await load();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <section className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Server className="w-5 h-5 text-amber-400" />
        <div>
          <h2 className="font-bold text-white">Simulator</h2>
          <p className="text-xs text-slate-400">
            Pretend systems the runbook steps act on. Break one, send an event, and watch what the app does.
          </p>
        </div>
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {services.map((s) => (
          <div key={s.name} className="border border-slate-800 rounded-lg p-3 space-y-2 bg-slate-950/40">
            <div className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${s.restarting ? 'bg-sky-400 animate-pulse' : s.healthy ? 'bg-emerald-500' : 'bg-red-500'}`} />
              <span className="font-mono text-sm text-slate-200">{s.name}</span>
            </div>
            <p className="text-xs text-slate-400">{s.restarting ? 'Restarting…' : s.healthy ? 'Up' : 'Down'}</p>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => toggle(s, 'healthy')}
                className={`text-xs px-2 py-1 rounded border ${s.healthy ? 'border-red-500/50 text-red-300 hover:bg-red-500/10' : 'border-emerald-500/50 text-emerald-300 hover:bg-emerald-500/10'}`}>
                {s.healthy ? 'Break it' : 'Fix it'}
              </button>
              {s.name === 'settlement' && (
                <button onClick={() => toggle(s, 'workflows_ok')}
                  className="text-xs px-2 py-1 rounded border border-slate-600 text-slate-300 hover:bg-slate-800">
                  Retries {s.workflows_ok ? 'succeed' : 'fail'}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">What the app did</h3>
        {calls.length === 0
          ? <p className="text-xs text-slate-500 italic">Nothing yet. Steps from alerts will show up here.</p>
          : (
            <ul className="space-y-1 text-xs font-mono">
              {calls.map((c) => (
                <li key={c.id} className="flex gap-3">
                  <span className="text-slate-500 shrink-0">{time(c.at)}</span>
                  <span className={c.ok ? 'text-emerald-400' : 'text-red-400'}>{c.ok ? '✓' : '✗'}</span>
                  <span className="text-slate-300 shrink-0">{c.action}</span>
                  <span className="text-slate-400 truncate">{c.detail}</span>
                  {c.alert_id && <a href={`#alerts/${c.alert_id}`} className="text-sky-400 hover:underline shrink-0">alert #{c.alert_id}</a>}
                </li>
              ))}
            </ul>
          )}
      </div>
    </section>
  );
}
