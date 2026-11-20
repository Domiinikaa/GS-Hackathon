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

export default function AlertCard({ alert }: { alert: Alert }) {
  const color = BAR[alert.color] ? alert.color : 'slate'; // nieznany kolor z backendu → szary

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
            {alert.team} · <span className={STATUS[alert.status]}>{alert.status}</span> · last seen {timeAgo(alert.last_seen)}
          </p>
        </div>

        {/* licznik deduplikacji – tylko gdy alert się powtórzył */}
        {alert.count > 1 && (
          <span className="shrink-0 font-mono text-sm font-bold text-white bg-slate-800 border border-slate-700 rounded-lg px-2 py-1"
            title={`This alert happened ${alert.count} times`}>
            ×{alert.count}
          </span>
        )}
      </div>
    </div>
  );
}
