// OSOBA 1 – lista alertów z filtrami, aktualizowana na żywo (SSE z /api/alerts/stream).
import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api } from '../shared/api';
import type { Alert, AlertStatus } from '../shared/types';
import AlertCard, { AlertAction } from './AlertCard';

type StatusFilter = AlertStatus | 'all';

export default function AlertsPage() {
  // "Pamięć" strony
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [status, setStatus] = useState<StatusFilter>('open');
  const [team, setTeam] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null); // który alert właśnie się zapisuje
  const [live, setLive] = useState(false);                    // czy "radio" jest podłączone
  const [liveMode, setLiveMode] = useState<string>('');       // in-memory / postgres-notify

  // Pobierz alerty z backendu. Filtr statusu robi backend (?status=…), zespołu – my niżej.
  async function load() {
    setLoading(true);
    setError(null);
    try {
      const query = status === 'all' ? '' : `?status=${status}`;
      setAlerts(await api<Alert[]>(`/alerts${query}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  // Kliknięcie Acknowledge / Resolve: POST /api/alerts/{id}/ack|resolve, potem odśwież listę
  async function handleAction(alert: Alert, action: AlertAction) {
    setBusyId(alert.id);
    setError(null);
    try {
      await api<Alert>(`/alerts/${alert.id}/${action}`, { method: 'POST' });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  // Uruchom load() przy otwarciu strony i za każdym razem, gdy zmieni się filtr statusu
  useEffect(() => {
    load();
  }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Na żywo: nastaw się na "radio" /api/alerts/stream. Każda wiadomość = alert, który się zmienił.
  useEffect(() => {
    const source = new EventSource('/api/alerts/stream');

    source.addEventListener('hello', (e) => {          // serwer potwierdza połączenie
      setLive(true);
      setLiveMode(JSON.parse((e as MessageEvent).data).mode);
    });
    source.onerror = () => setLive(false);             // przeglądarka sama spróbuje połączyć się ponownie

    source.onmessage = (e) => {
      const changed: Alert = JSON.parse(e.data);
      setAlerts((prev) => {
        const rest = prev.filter((a) => a.id !== changed.id);         // wyrzuć starą wersję tej karty
        const fits = status === 'all' || changed.status === status;   // czy pasuje do filtra statusu
        return fits ? [changed, ...rest] : rest;                      // nowa wersja na górę listy
      });
    };

    return () => source.close();                       // wyjście z zakładki / zmiana filtra = wyłącz radio
  }, [status]);

  // Lista zespołów do filtra – zbudowana z tego, co jest w alertach
  const teams = Array.from(new Set(alerts.map((a) => a.team))).sort();
  const visible = team === 'all' ? alerts : alerts.filter((a) => a.team === team);

  const selectClass =
    'bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-amber-500';

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            Alerts
            <span className={`flex items-center gap-1.5 text-xs font-medium ${live ? 'text-emerald-400' : 'text-slate-500'}`}
              title={live ? `Live updates on (${liveMode})` : 'Live updates disconnected – use Refresh'}>
              <span className={`w-2 h-2 rounded-full ${live ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}`} />
              {live ? 'Live' : 'Offline'}
            </span>
          </h1>
          <p className="text-sm text-slate-400">What needs attention right now.</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select value={team} onChange={(e) => setTeam(e.target.value)} className={selectClass} aria-label="Team">
            <option value="all">All teams</option>
            {teams.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value as StatusFilter)} className={selectClass} aria-label="Status">
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
            <option value="all">All statuses</option>
          </select>
          <button onClick={load}
            className="flex items-center gap-1.5 text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg border border-slate-700">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
          Could not load alerts: {error}
        </div>
      )}

      <div className="space-y-3">
        {visible.map((a) => (
          <AlertCard key={a.id} alert={a} onAction={handleAction} busy={busyId === a.id} />
        ))}

        {!loading && !error && visible.length === 0 && (
          <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
            <p className="text-slate-400">No alerts here.</p>
            <p className="text-xs text-slate-600 mt-1">
              Tip: create a test alert with <code className="text-amber-400">POST /api/alerts/test</code> in <a href="/docs" target="_blank" rel="noreferrer" className="underline">/docs</a>.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
