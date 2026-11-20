// OSOBA 1 – wygląd JEDNEGO alertu na liście.
// Kolor i ważność biorą się z reguły (wymaganie 2.2 "per-rule presentation").
import type { Alert } from '../shared/types';
import type { Color } from '../rules/ruleTypes';

// Tailwind potrzebuje pełnych nazw klas wpisanych w kodzie, dlatego mapy zamiast `bg-${color}-500`
const BAR: Record<Color, string> = {
  red: 'bg-red-500',
  amber: 'bg-amber-500',
  blue: 'bg-blue-500',
  green: 'bg-emerald-500',
  slate: 'bg-slate-500',
};

const BADGE: Record<Color, string> = {
  red: 'bg-red-500/15 text-red-400 border-red-500/30',
  amber: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  blue: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  green: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  slate: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
};

const STATUS: Record<Alert['status'], string> = {
  open: 'text-red-400',
  acknowledged: 'text-amber-400',
  resolved: 'text-emerald-400',
};

// Backend zapisuje czas w UTC bez strefy ("2026-11-20T22:02:06"). Dopisujemy "Z",
// żeby przeglądarka nie potraktowała go jako czasu lokalnego.
function parseUtc(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z');
}

// "2 min ago", "3 h ago" – ile czasu minęło od daty
export function timeAgo(iso: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - parseUtc(iso).getTime()) / 1000));
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.floor(hours / 24)} d ago`;
}

export type AlertAction = 'ack' | 'resolve';

interface Props {
  alert: Alert;
  onAction: (alert: Alert, action: AlertAction) => void;
  busy?: boolean; // true = trwa wysyłanie kliknięcia, przyciski wyłączone
}

export default function AlertCard({ alert, onAction, busy = false }: Props) {
  const color = BAR[alert.color] ? alert.color : 'slate'; // nieznany kolor z backendu → szary
  // Kto ostatnio zmienił status – ostatni wpis historii (pomijamy "system created")
  const last = alert.history?.length ? alert.history[alert.history.length - 1] : null;
  const changedBy = last && last.who !== 'system' ? last.who : null;

  return (
    <div className="relative bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
      {/* kolorowy pasek z lewej */}
      <div className={`absolute inset-y-0 left-0 w-1.5 ${BAR[color]}`} />

      <div className="pl-5 pr-4 py-4 flex items-start gap-4">
        <span className={`shrink-0 mt-0.5 text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded border ${BADGE[color]}`}>
          {alert.severity}
        </span>

        <div className="flex-1 min-w-0">
          <p className="font-semibold text-white truncate">{alert.title}</p>
          {alert.body && <p className="text-sm text-slate-400 mt-0.5">{alert.body}</p>}
          <p className="text-xs text-slate-500 mt-2">
            {alert.team} · <span className={STATUS[alert.status]}>{alert.status}</span>
            {changedBy && <> by {changedBy}</>} · last seen {timeAgo(alert.last_seen)}
          </p>
        </div>

        <div className="shrink-0 flex flex-col items-end gap-2">
          {/* licznik deduplikacji – tylko gdy alert się powtórzył */}
          {alert.count > 1 && (
            <span className="font-mono text-sm font-bold text-white bg-slate-800 border border-slate-700 rounded-lg px-2 py-1"
              title={`This alert happened ${alert.count} times`}>
              ×{alert.count}
            </span>
          )}

          {/* przyciski – tylko te, które mają sens dla obecnego statusu */}
          <div className="flex gap-2">
            {alert.status === 'open' && (
              <button disabled={busy} onClick={() => onAction(alert, 'ack')}
                className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-amber-500/40 text-amber-300 hover:bg-amber-500/10 disabled:opacity-50">
                Acknowledge
              </button>
            )}
            {alert.status !== 'resolved' && (
              <button disabled={busy} onClick={() => onAction(alert, 'resolve')}
                className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-50">
                Resolve
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
