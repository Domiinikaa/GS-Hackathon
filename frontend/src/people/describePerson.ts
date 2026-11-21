// Labels and text for people preferences.
import { CHANNELS, Channel, Severity } from '../rules/ruleTypes';
import type { Person } from '../shared/types';

// Most important first
export const SEVERITY_ORDER: Severity[] = ['critical', 'warning', 'info'];

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'Critical',
  warning: 'Warning',
  info: 'Info',
};

export const SEVERITY_STYLE: Record<Severity, string> = {
  critical: 'text-red-300 bg-red-500/10 border-red-500/30',
  warning: 'text-amber-300 bg-amber-500/10 border-amber-500/30',
  info: 'text-blue-300 bg-blue-500/10 border-blue-500/30',
};

export function channelLabel(ch: Channel | string): string {
  return CHANNELS.find((c) => c.value === ch)?.label ?? ch;
}

export function describeQuietHours(person: Pick<Person, 'quiet_hours'>): string[] {
  return Object.entries(person.quiet_hours ?? {})
    .filter(([, w]) => w && w.from && w.to)
    .map(([ch, w]) => {
      const fallback = w!.else ? `otherwise ${channelLabel(w!.else)}` : 'otherwise skipped';
      return `${channelLabel(ch)} only ${w!.from}–${w!.to}, ${fallback}`;
    });
}
