// OSOBA 1 – wygląd JEDNEGO alertu na liście.
// Kolor i ważność biorą się z reguły (wymaganie 2.2 "per-rule presentation").
import { ChevronDown } from 'lucide-react';
import type { Alert } from '../shared/types';
import type { Color } from '../rules/ruleTypes';
import AlertDetails from './AlertDetails';

// Tailwind potrzebuje pełnych nazw klas wpisanych w kodzie, dlatego mapa zamiast `bg-${color}-500`
const DOT: Record<Color, string> = {
  red: 'bg-ios-red',
  amber: 'bg-ios-orange',
  blue: 'bg-ios-blue',
  green: 'bg-ios-green',
  slate: 'bg-ink-faint',
};

const STATUS: Record<Alert['status'], string> = {
  open: 'text-ios-red',
  acknowledged: 'text-ios-orange',
  resolved: 'text-ios-green',
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

// ack/resolve dotyczą całego alertu, approve/done/retry – jednego kroku runbooka (stepIndex)
export type AlertAction = 'ack' | 'resolve' | 'approve' | 'done' | 'retry';
export type OnAlertAction = (alert: Alert, action: AlertAction, stepIndex?: number) => void;

interface Props {
  alert: Alert;
  onAction: OnAlertAction;
  busy?: boolean;       // true = trwa wysyłanie kliknięcia, przyciski wyłączone
  expanded?: boolean;   // czy pokazać szczegóły (kroki runbooka, historia)
  onToggle?: () => void;
}

export default function AlertCard({ alert, onAction, busy = false, expanded = false, onToggle }: Props) {
  const color = DOT[alert.color] ? alert.color : 'slate'; // nieznany kolor z backendu → szary
  // Kto ustawił obecny status – ostatni wpis historii o TYM statusie (pomijamy kroki runbooka i "created")
  const statusEntry = [...(alert.history ?? [])].reverse().find((h) => h.what === alert.status);
  const changedBy = statusEntry && statusEntry.who !== 'system' ? statusEntry.who : null;

  return (
    <div id={`alert-${alert.id}`} className="ios-divided">
      <div className="ios-row items-start py-3">
        {/* klik w treść rozwija / zwija szczegóły */}
        <button type="button" onClick={onToggle} aria-expanded={expanded}
          className="flex-1 min-w-0 text-left flex items-start gap-3">
          <span className={`mt-[7px] w-2.5 h-2.5 rounded-full shrink-0 ${DOT[color]}`} aria-hidden="true" />
          <span className="min-w-0">
            <span className="block text-[15px] font-semibold text-white truncate">{alert.title}</span>
            <span className="block text-[13px] text-ink-muted mt-0.5">
              {alert.team}, <span className={STATUS[alert.status]}>{alert.status}</span>
              {changedBy && <> by {changedBy}</>}
            </span>
            {alert.body && !expanded && <span className="block text-[13px] text-ink-muted mt-0.5 truncate">{alert.body}</span>}
          </span>
        </button>

        <div className="shrink-0 flex flex-col items-end gap-1.5">
          <span className="flex items-center gap-1 text-[13px] text-ink-muted">
            {timeAgo(alert.last_seen)}
            <ChevronDown className={`w-4 h-4 text-ink-faint transition-transform duration-300 ${expanded ? 'rotate-180' : ''}`} />
          </span>
          {/* licznik deduplikacji – tylko gdy alert się powtórzył */}
          {alert.count > 1 && (
            <span className="min-w-[22px] h-[22px] px-1.5 rounded-full bg-ios-fill text-[12px] font-semibold text-white flex items-center justify-center tabular-nums"
              title={`This alert happened ${alert.count} times`}>
              {alert.count}
            </span>
          )}
        </div>
      </div>

      {/* przyciski – tylko te, które mają sens dla obecnego statusu */}
      {alert.status !== 'resolved' && (
        <div className="flex gap-2 px-4 pb-3 pl-[38px]">
          {alert.status === 'open' && (
            <button disabled={busy} onClick={() => onAction(alert, 'ack')}
              className="h-8 px-3.5 rounded-full bg-ios-fill text-[13px] font-semibold text-ios-orange hover:bg-white/[0.16] transition-colors disabled:opacity-40">
              Acknowledge
            </button>
          )}
          <button disabled={busy} onClick={() => onAction(alert, 'resolve')}
            className="h-8 px-3.5 rounded-full bg-ios-fill text-[13px] font-semibold text-ios-green hover:bg-white/[0.16] transition-colors disabled:opacity-40">
            Resolve
          </button>
        </div>
      )}

      {expanded && <AlertDetails alert={alert} onAction={onAction} busy={busy} />}
    </div>
  );
}
