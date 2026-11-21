// OSOBA 1 – wygląd JEDNEGO alertu na liście.
// Kolor i ważność biorą się z reguły (wymaganie 2.2 "per-rule presentation").
import { ChevronDown } from 'lucide-react';
import type { Alert } from '../shared/types';
import type { Color } from '../rules/ruleTypes';
import AlertDetails from './AlertDetails';
import { SeverityBadge } from '../shared/ui';

// Tailwind potrzebuje pełnych nazw klas wpisanych w kodzie, dlatego mapy zamiast `bg-${color}-500`
const BAR: Record<Color, string> = {
  red: 'bg-rose-400 shadow-[0_0_14px_rgba(244,63,94,0.7)]',
  amber: 'bg-amber-400 shadow-[0_0_14px_rgba(245,158,11,0.6)]',
  blue: 'bg-sky-400 shadow-[0_0_14px_rgba(56,189,248,0.5)]',
  green: 'bg-emerald-400 shadow-[0_0_14px_rgba(52,211,153,0.5)]',
  slate: 'bg-slate-400',
};

const BADGE: Record<Color, string> = {
  red: 'bg-red-500/15 text-rose-300 border-rose-500/30',
  amber: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  blue: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  green: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  slate: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
};

const STATUS: Record<Alert['status'], string> = {
  open: 'text-rose-300',
  acknowledged: 'text-amber-400',
  resolved: 'text-emerald-400',
};

// Backend zapisuje czas w UTC bez strefy ("2026-11-20T22:02:06"). Dopisujemy "Z",
// żeby przeglądarka nie potraktowała go jako czasu lokalnego.
export function parseUtc(iso: string): Date {
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

// ack/resolve dotyczą całego alertu, approve/done – jednego kroku runbooka (stepIndex)
export type AlertAction = 'ack' | 'resolve' | 'approve' | 'done';
export type OnAlertAction = (alert: Alert, action: AlertAction, stepIndex?: number) => void;

interface Props {
  alert: Alert;
  onAction: OnAlertAction;
  busy?: boolean;       // true = trwa wysyłanie kliknięcia, przyciski wyłączone
  expanded?: boolean;   // czy pokazać szczegóły (kroki runbooka, historia)
  onToggle?: () => void;
}

export default function AlertCard({ alert, onAction, busy = false, expanded = false, onToggle }: Props) {
  const color = BAR[alert.color] ? alert.color : 'slate'; // nieznany kolor z backendu → szary
  // Kto ustawił obecny status – ostatni wpis historii o TYM statusie (pomijamy kroki runbooka i "created")
  const statusEntry = [...(alert.history ?? [])].reverse().find((h) => h.what === alert.status);
  const changedBy = statusEntry && statusEntry.who !== 'system' ? statusEntry.who : null;

  return (
    <div id={`alert-${alert.id}`}
      className={`glass-card relative overflow-hidden ${expanded ? '!border-white/20' : ''}`}>
      {/* kolorowy pasek z lewej, z poświatą */}
      <div className={`absolute inset-y-3 left-0 w-1 rounded-r-full ${BAR[color]}`} />

      <div className="pl-6 pr-5 py-5 flex items-start gap-4">
        <SeverityBadge severity={alert.severity} className="shrink-0 mt-0.5" />

        {/* klik w treść karty rozwija / zwija szczegóły */}
        <button type="button" onClick={onToggle} aria-expanded={expanded}
          className="flex-1 min-w-0 text-left group">
          <p className="text-[16px] font-semibold text-white truncate flex items-center gap-1.5">
            <span className="truncate">{alert.title}</span>
            <ChevronDown className={`w-4 h-4 shrink-0 text-ink-muted transition-transform duration-300 ${expanded ? 'rotate-180' : ''}`} />
          </p>
          {alert.body && !expanded && <p className="text-sm text-ink-muted mt-1 truncate">{alert.body}</p>}
          <p className="text-xs text-ink-muted mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="text-slate-200">{alert.team}</span>
            <span><span className={`capitalize ${STATUS[alert.status]}`}>{alert.status}</span>{changedBy && <> by {changedBy}</>}</span>
            <span>Last seen {timeAgo(alert.last_seen)}</span>
          </p>
        </button>

        <div className="shrink-0 flex flex-col items-end gap-2">
          {/* licznik deduplikacji – tylko gdy alert się powtórzył */}
          {alert.count > 1 && (
            <span className="glass-pill font-mono text-sm font-semibold text-white px-2.5 py-0.5"
              title={`This alert happened ${alert.count} times`}>
              ×{alert.count}
            </span>
          )}

          {/* przyciski – tylko te, które mają sens dla obecnego statusu */}
          <div className="flex gap-2">
            {alert.status === 'open' && (
              <button disabled={busy} onClick={() => onAction(alert, 'ack')}
                className="text-xs font-semibold px-3.5 py-1.5 rounded-full border border-amber-500/40 bg-amber-500/10 text-amber-200 hover:bg-amber-500/20 transition-colors disabled:opacity-50">
                Acknowledge
              </button>
            )}
            {alert.status !== 'resolved' && (
              <button disabled={busy} onClick={() => onAction(alert, 'resolve')}
                className="text-xs font-semibold px-3.5 py-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20 transition-colors disabled:opacity-50">
                Resolve
              </button>
            )}
          </div>
        </div>
      </div>

      {expanded && <AlertDetails alert={alert} onAction={onAction} busy={busy} />}
    </div>
  );
}
