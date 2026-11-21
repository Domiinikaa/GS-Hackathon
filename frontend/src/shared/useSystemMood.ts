// System mood drives the living backdrop: it summarises open alerts into one state
// and writes it to <html data-mood> + --mood-strength so CSS can light the right glow.
import { useEffect, useState } from 'react';
import { api } from './api';
import type { Alert } from './types';

export type Mood = 'idle' | 'clear' | 'warning' | 'critical';

export interface SystemMood {
  mood: Mood;
  critical: number;
  warning: number;
}

const POLL_MS = 15_000;

function summarise(alerts: Alert[]): SystemMood {
  const open = alerts.filter((a) => a.status === 'open');
  const critical = open.filter((a) => a.severity === 'critical').length;
  const warning = open.filter((a) => a.severity === 'warning').length;
  const mood: Mood = critical > 0 ? 'critical' : warning > 0 ? 'warning' : 'clear';
  return { mood, critical, warning };
}

export function useSystemMood(enabled: boolean): SystemMood {
  const [state, setState] = useState<SystemMood>({ mood: 'idle', critical: 0, warning: 0 });

  useEffect(() => {
    if (!enabled) {
      setState({ mood: 'idle', critical: 0, warning: 0 });
      return;
    }

    let cancelled = false;
    const refresh = async () => {
      try {
        const alerts = await api<Alert[]>('/alerts?status=open');
        if (!cancelled) setState(summarise(alerts));
      } catch {
        // Keep the last known mood; the alerts page reports errors itself.
      }
    };

    refresh();
    const timer = window.setInterval(refresh, POLL_MS);
    // Any alert change on the live stream means the mood may have changed.
    const stream = new EventSource('/api/alerts/stream');
    stream.onmessage = () => refresh();

    return () => {
      cancelled = true;
      window.clearInterval(timer);
      stream.close();
    };
  }, [enabled]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.mood = state.mood;
    // More open alerts = stronger glow, capped so text stays readable.
    const count = state.mood === 'critical' ? state.critical : state.warning;
    const strength = state.mood === 'clear' ? 1 : Math.min(1, 0.55 + count * 0.15);
    root.style.setProperty('--mood-strength', String(strength));
  }, [state]);

  return state;
}

export function describeMood({ mood, critical, warning }: SystemMood): string {
  if (mood === 'idle') return 'Checking alerts';
  if (mood === 'clear') return 'All clear';
  if (mood === 'critical') return `${critical} critical open`;
  return `${warning} ${warning === 1 ? 'warning' : 'warnings'} open`;
}
