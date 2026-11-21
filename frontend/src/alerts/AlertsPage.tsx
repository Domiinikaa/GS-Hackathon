// OSOBA 1 – lista alertów z filtrami, aktualizowana na żywo (SSE z /api/alerts/stream).
import { useEffect, useState } from 'react';
import { RefreshCw, BellOff } from 'lucide-react';
import { EmptyState, Notice } from '../shared/ui';
import { api } from '../shared/api';
import { errorMessage } from '../rules/rulesApi';
import type { Alert, AlertStatus } from '../shared/types';
import type { User } from '../types';
import AlertCard, { AlertAction } from './AlertCard';

type StatusFilter = AlertStatus | 'all';

// Link do konkretnego alertu (np. w SMS-ie): #alerts/5 – otwiera stronę z rozwiniętym alertem nr 5
function alertIdFromUrl(): number | null {
  const m = window.location.hash.match(/^#alerts\/(\d+)/);
  return m ? Number(m[1]) : null;
}

export default function AlertsPage({ currentUser }: { currentUser?: User | null } = {}) {
  // "Pamięć" strony
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [knownTeams, setKnownTeams] = useState<string[]>([]);
  const linkedId = alertIdFromUrl();
  // Wejście z linku: pokaż wszystkie statusy, żeby alert był widoczny nawet gdy już acknowledged
  const [status, setStatus] = useState<StatusFilter>(linkedId ? 'all' : 'open');
  const [team, setTeam] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null); // który alert właśnie się zapisuje
  const [live, setLive] = useState(false);                    // czy "radio" jest podłączone
  const [liveMode, setLiveMode] = useState<string>('');       // in-memory / postgres-notify
  const [expandedId, setExpandedId] = useState<number | null>(linkedId); // który alert ma rozwinięte szczegóły

  // Rozwiń / zwiń alert. Adres w pasku zmienia się na #alerts/<id>, więc można go skopiować i wysłać.
  // replaceState zamiast location.hash – nie przełącza zakładek w App.tsx.
  function toggle(id: number) {
    const next = expandedId === id ? null : id;
    setExpandedId(next);
    window.history.replaceState(null, '', next ? `#alerts/${next}` : '#alerts');
  }

  // Link #alerts/<id> wklejony do już otwartej strony (zmienia się tylko # – strona się nie przeładowuje)
  useEffect(() => {
    const onHash = () => {
      const id = alertIdFromUrl();
      if (id) {
        setStatus('all');
        setExpandedId(id);
      }
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // Przewiń do rozwiniętego alertu, gdy jest już na liście
  useEffect(() => {
    if (expandedId) document.getElementById(`alert-${expandedId}`)?.scrollIntoView({ block: 'nearest' });
  }, [expandedId, alerts.length > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  // Pobierz alerty z backendu. Filtr statusu robi backend (?status=…), zespołu – my niżej.
  async function load() {
    setLoading(true);
    setError(null);
    try {
      const query = status === 'all' ? '' : `?status=${status}`;
      setAlerts(await api<Alert[]>(`/alerts${query}`));
    } catch (e) {
      setError(`Could not load alerts: ${errorMessage(e)}`);
    } finally {
      setLoading(false);
    }
  }

  // Kliknięcie Acknowledge / Resolve (cały alert) albo Approve / Mark done (jeden krok runbooka)
  async function handleAction(alert: Alert, action: AlertAction, stepIndex?: number) {
    setBusyId(alert.id);
    setError(null);
    const path = action === 'approve' || action === 'done'
      ? `/alerts/${alert.id}/steps/${stepIndex}/${action}`
      : `/alerts/${alert.id}/${action}`;
    try {
      await api<Alert>(path, { method: 'POST' });
      await load();
    } catch (e) {
      setError(errorMessage(e));
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

    let connectedBefore = false;
    source.addEventListener('hello', (e) => {          // serwer potwierdza połączenie
      setLive(true);
      setLiveMode(JSON.parse((e as MessageEvent).data).mode);
      // Ponowne połączenie (np. po zerwaniu Wi-Fi): zmiany z czasu przerwy nie przyszły – pobierz listę od nowa
      if (connectedBefore) load();
      connectedBefore = true;
    });
    source.onerror = () => setLive(false);             // przeglądarka sama spróbuje połączyć się ponownie

    source.onmessage = (e) => {
      const changed: Alert = JSON.parse(e.data);
      setAlerts((prev) => {
        const fits = status === 'all' || changed.status === status;   // czy pasuje do filtra statusu
        if (!fits) return prev.filter((a) => a.id !== changed.id);    // np. rozwiązany przy filtrze Open – znika
        const known = prev.some((a) => a.id === changed.id);
        return known
          ? prev.map((a) => (a.id === changed.id ? changed : a))      // znany alert: podmień w miejscu (karta nie skacze)
          : [changed, ...prev];                                        // nowy alert: na górę listy
      });
    };

    return () => source.close();                       // wyjście z zakładki / zmiana filtra = wyłącz radio
  }, [status]);

  // Pobierz kanoniczną listę zespołów (Admin & Teams)
  useEffect(() => {
    api<{ id: number; name: string }[]>('/teams')
      .then((list) => setKnownTeams(list.map((t) => t.name)))
      .catch(() => {});
  }, []);

  // Lista zespołów do filtra – kanoniczne zespoły + wartości z alertów
  const teams = Array.from(new Set([...knownTeams, ...alerts.map((a) => a.team)])).sort();
  const visible = team === 'all' ? alerts : alerts.filter((a) => a.team === team);
  const userTeam = currentUser?.team ?? currentUser?.dzial;

  const selectClass =
    'field h-9 px-3 text-sm !rounded-full';

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white flex items-center gap-3">
            Alerts
            <span className={`flex items-center gap-1.5 text-xs font-medium ${live ? 'text-emerald-400' : 'text-slate-500'}`}
              title={live ? `Live updates on (${liveMode})` : 'Live updates disconnected – use Refresh'}>
              <span className={`w-2 h-2 rounded-full ${live ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}`} />
              {live ? 'Live' : 'Offline'}
            </span>
          </h1>
          <p className="mt-1.5 text-sm text-ink-muted">What needs attention right now.</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {userTeam && (
            <button
              type="button"
              onClick={() => setTeam(team === userTeam ? 'all' : userTeam)}
              className={`text-sm font-medium px-4 h-9 rounded-full border transition-colors ${
                team === userTeam
                  ? 'bg-gs-gold/15 border-gs-gold/50 text-gs-gold'
                  : 'glass-pill text-slate-200 hover:bg-white/10'
              }`}
            >
              My team ({userTeam})
            </button>
          )}
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
            className="glass-pill h-9 px-4 text-sm font-medium text-slate-200 hover:bg-white/10 transition-colors">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <Notice tone="error">{error}</Notice>
      )}

      <div className="space-y-3">
        {visible.map((a) => (
          <AlertCard key={a.id} alert={a} onAction={handleAction} busy={busyId === a.id}
            expanded={expandedId === a.id} onToggle={() => toggle(a.id)} />
        ))}

        {!loading && !error && visible.length === 0 && (
          <EmptyState icon={BellOff} title="Nothing needs attention"
            text={<>No alerts match these filters. To try it out, send a test alert with <code className="font-mono text-gs-gold">POST /api/alerts/test</code> in <a href="/docs" target="_blank" rel="noreferrer" className="underline hover:text-white">API docs</a>.</>} />
        )}
      </div>
    </div>
  );
}
