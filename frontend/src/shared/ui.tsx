// Shared Liquid Glass UI pieces, so every page looks like it was made by one person.
import type { ReactNode } from 'react';
import { Loader2, Mail, MessageSquare, Monitor, Phone, type LucideIcon } from 'lucide-react';
import { twMerge } from 'tailwind-merge';
import clsx, { type ClassValue } from 'clsx';

export function cn(...classes: ClassValue[]) {
  return twMerge(clsx(classes));
}

// ---------------------------------------------------------------- page header

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-4 flex-wrap">
      <div className="min-w-0">
        <h1 className="text-3xl font-semibold tracking-tight text-white">{title}</h1>
        {description && <p className="mt-1.5 text-sm text-ink-muted max-w-2xl">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- severity

export type SeverityLevel = 'critical' | 'warning' | 'info';

const SEVERITY_BADGE: Record<SeverityLevel, string> = {
  critical: 'bg-rose-500/10 text-rose-300 border-rose-500/30 shadow-[0_0_20px_rgba(244,63,94,0.15)]',
  warning: 'bg-amber-500/10 text-amber-300 border-amber-500/30 shadow-[0_0_20px_rgba(245,158,11,0.15)]',
  info: 'bg-sky-500/10 text-sky-300 border-sky-500/30',
};

export const SEVERITY_DOT: Record<SeverityLevel, string> = {
  critical: 'bg-rose-400',
  warning: 'bg-amber-400',
  info: 'bg-sky-400',
};

export function SeverityBadge({ severity, className }: { severity: string; className?: string }) {
  const level = (severity in SEVERITY_BADGE ? severity : 'info') as SeverityLevel;
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-0.5 rounded-full border capitalize', SEVERITY_BADGE[level], className)}>
      <span className={cn('w-1.5 h-1.5 rounded-full', SEVERITY_DOT[level])} />
      {severity}
    </span>
  );
}

// ---------------------------------------------------------------- channels

const CHANNEL_META: Record<string, { label: string; icon: LucideIcon; color: string }> = {
  email: { label: 'Email', icon: Mail, color: 'text-sky-300' },
  sms: { label: 'SMS', icon: MessageSquare, color: 'text-emerald-300' },
  phone: { label: 'Phone', icon: Phone, color: 'text-violet-300' },
  ui: { label: 'UI', icon: Monitor, color: 'text-amber-300' },
};

export function ChannelPill({ channel }: { channel: string }) {
  const meta = CHANNEL_META[channel] ?? { label: channel, icon: Monitor, color: 'text-ink-muted' };
  const Icon = meta.icon;
  return (
    <span className="glass-pill px-2.5 py-0.5 text-xs font-medium text-ink">
      <Icon className={cn('w-3.5 h-3.5', meta.color)} aria-hidden="true" />
      {meta.label}
    </span>
  );
}

// ---------------------------------------------------------------- toggle

export function Toggle({ checked, onChange, label, className }: { checked: boolean; onChange: () => void; label: string; className?: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} title={label}
      onClick={onChange} className={cn('switch', className)} />
  );
}

// ---------------------------------------------------------------- notices

const NOTICE_TONE = {
  error: 'bg-rose-500/10 text-rose-200 border-rose-500/25',
  success: 'bg-emerald-500/10 text-emerald-200 border-emerald-500/25',
  warning: 'bg-amber-500/10 text-amber-200 border-amber-500/25',
  info: 'bg-sky-500/10 text-sky-200 border-sky-500/25',
};

export function Notice({ tone, children, className }: { tone: keyof typeof NOTICE_TONE; children: ReactNode; className?: string }) {
  return (
    <div role={tone === 'error' ? 'alert' : 'status'}
      className={cn('flex items-start gap-2 text-sm rounded-xl border px-4 py-2.5 backdrop-blur-xl', NOTICE_TONE[tone], className)}>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------- empty + loading

export function EmptyState({ icon: Icon, title, text, action }: { icon: LucideIcon; title: string; text?: ReactNode; action?: ReactNode }) {
  return (
    <div className="glass-card glass-card--static px-6 py-12 flex flex-col items-center text-center">
      <span className="glass-pill w-12 h-12 justify-center !rounded-2xl">
        <Icon className="w-5 h-5 text-ink-muted" aria-hidden="true" />
      </span>
      <p className="mt-4 text-base font-semibold text-white">{title}</p>
      {text && <p className="mt-1 text-sm text-ink-muted max-w-sm">{text}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-sm text-ink-muted" role="status">
      <Loader2 className="w-4 h-4 animate-spin text-gs-gold" aria-hidden="true" />
      {label}
    </div>
  );
}

// ---------------------------------------------------------------- buttons

export const iconButton =
  'w-9 h-9 rounded-full flex items-center justify-center text-ink-muted hover:text-white hover:bg-white/[0.08] transition-colors';
export const secondaryButton =
  'glass-pill px-4 h-10 justify-center text-sm font-medium text-ink hover:bg-white/10 hover:border-white/20 transition-colors disabled:opacity-40';
export const ghostButton =
  'text-sm font-medium text-ink-muted hover:text-white px-3 h-10 rounded-full hover:bg-white/[0.06] transition-colors';
