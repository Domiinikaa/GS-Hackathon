// Shared iOS-style UI pieces (dark appearance). Every page builds from these,
// so the app reads like one native iPhone app instead of separate screens.
import type { ReactNode } from 'react';
import { ChevronRight, Loader2, Mail, MessageSquare, Monitor, Phone, type LucideIcon } from 'lucide-react';
import { twMerge } from 'tailwind-merge';
import clsx, { type ClassValue } from 'clsx';

export function cn(...classes: ClassValue[]) {
  return twMerge(clsx(classes));
}

// ---------------------------------------------------------------- large title

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-4 flex-wrap pt-2">
      <div className="min-w-0">
        <h1 className="text-[34px] leading-[41px] font-bold text-white">{title}</h1>
        {description && <p className="mt-1 text-[15px] text-ink-muted max-w-2xl">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- grouped lists

/** A titled block of grouped cells, like a section in iOS Settings. */
export function Section({ title, footer, action, children, className }: {
  title?: ReactNode; footer?: ReactNode; action?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={className}>
      {(title || action) && (
        <div className="flex items-end justify-between gap-3 px-4 pb-1.5">
          {title && <h2 className="text-[13px] font-normal text-ink-muted">{title}</h2>}
          {action}
        </div>
      )}
      <div className="ios-group">{children}</div>
      {footer && <p className="px-4 pt-1.5 text-[13px] text-ink-muted">{footer}</p>}
    </section>
  );
}

/** One cell: optional icon, label on the left, value on the right, optional chevron. */
export function Row({ icon, label, sublabel, value, accessory, chevron, onClick, className }: {
  icon?: ReactNode; label: ReactNode; sublabel?: ReactNode; value?: ReactNode; accessory?: ReactNode;
  chevron?: boolean; onClick?: () => void; className?: string;
}) {
  const content = (
    <>
      {icon}
      <div className="flex-1 min-w-0">
        <div className="text-[15px] text-white truncate">{label}</div>
        {sublabel && <div className="text-[13px] text-ink-muted mt-0.5">{sublabel}</div>}
      </div>
      {value !== undefined && <div className="text-[15px] text-ink-muted text-right min-w-0 max-w-[60%]">{value}</div>}
      {accessory}
      {chevron && <ChevronRight className="w-4 h-4 text-ink-faint shrink-0" aria-hidden="true" />}
    </>
  );
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={cn('ios-row ios-row--tap w-full text-left', className)}>
        {content}
      </button>
    );
  }
  return <div className={cn('ios-row', className)}>{content}</div>;
}

/** Rounded-square colored icon, as used in iOS Settings rows. */
export function RowIcon({ icon: Icon, color }: { icon: LucideIcon; color: string }) {
  return (
    <span className={cn('w-[29px] h-[29px] rounded-[7px] flex items-center justify-center shrink-0', color)} aria-hidden="true">
      <Icon className="w-[17px] h-[17px] text-white" strokeWidth={2.2} />
    </span>
  );
}

// ---------------------------------------------------------------- severity

export type SeverityLevel = 'critical' | 'warning' | 'info';

export const SEVERITY_DOT: Record<SeverityLevel, string> = {
  critical: 'bg-ios-red',
  warning: 'bg-ios-orange',
  info: 'bg-ios-blue',
};

const SEVERITY_TEXT: Record<SeverityLevel, string> = {
  critical: 'text-ios-red',
  warning: 'text-ios-orange',
  info: 'text-ios-blue',
};

export function SeverityBadge({ severity, className }: { severity: string; className?: string }) {
  const level = (severity in SEVERITY_DOT ? severity : 'info') as SeverityLevel;
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-[13px] font-semibold capitalize', SEVERITY_TEXT[level], className)}>
      <span className={cn('w-2 h-2 rounded-full', SEVERITY_DOT[level])} />
      {severity}
    </span>
  );
}

// ---------------------------------------------------------------- channels

export const CHANNEL_META: Record<string, { label: string; icon: LucideIcon; color: string }> = {
  email: { label: 'Email', icon: Mail, color: 'bg-ios-blue' },
  sms: { label: 'SMS', icon: MessageSquare, color: 'bg-ios-green' },
  phone: { label: 'Phone', icon: Phone, color: 'bg-ios-green' },
  ui: { label: 'In app', icon: Monitor, color: 'bg-ios-indigo' },
};

/** Small colored channel icon with its name. */
export function ChannelPill({ channel }: { channel: string }) {
  const meta = CHANNEL_META[channel] ?? { label: channel, icon: Monitor, color: 'bg-ios-raised' };
  const Icon = meta.icon;
  return (
    <span className="inline-flex items-center gap-1.5 text-[15px] text-ink-muted">
      <span className={cn('w-5 h-5 rounded-[5px] flex items-center justify-center', meta.color)} aria-hidden="true">
        <Icon className="w-3 h-3 text-white" strokeWidth={2.4} />
      </span>
      {meta.label}
    </span>
  );
}

export function ChannelList({ channels }: { channels: string[] }) {
  if (channels.length === 0) return <span className="text-ink-muted">None</span>;
  return (
    <span className="inline-flex flex-wrap justify-end gap-x-3 gap-y-1">
      {channels.map((c) => <ChannelPill key={c} channel={c} />)}
    </span>
  );
}

// ---------------------------------------------------------------- controls

export function Toggle({ checked, onChange, label, className }: { checked: boolean; onChange: () => void; label: string; className?: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} title={label}
      onClick={(e) => { e.stopPropagation(); onChange(); }} className={cn('switch', className)} />
  );
}

/** iOS segmented control. */
export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex p-0.5 rounded-[9px] bg-ios-fill max-w-full overflow-x-auto [scrollbar-width:none]">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
          className={cn('px-3.5 h-[30px] rounded-[7px] text-[13px] font-medium whitespace-nowrap transition-colors',
            value === o.value ? 'bg-[#636366] text-white shadow-[0_3px_8px_rgba(0,0,0,0.12)]' : 'text-white/80 hover:text-white')}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- notices

const NOTICE_TONE = {
  error: 'text-ios-red',
  success: 'text-ios-green',
  warning: 'text-ios-orange',
  info: 'text-ios-blue',
};

export function Notice({ tone, children, className }: { tone: keyof typeof NOTICE_TONE; children: ReactNode; className?: string }) {
  return (
    <div role={tone === 'error' ? 'alert' : 'status'}
      className={cn('ios-group flex items-start gap-2 text-[15px] px-4 py-3', NOTICE_TONE[tone], className)}>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------- empty + loading

export function EmptyState({ icon: Icon, title, text, action }: { icon: LucideIcon; title: string; text?: ReactNode; action?: ReactNode }) {
  return (
    <div className="px-6 py-16 flex flex-col items-center text-center">
      <Icon className="w-11 h-11 text-ink-faint" strokeWidth={1.5} aria-hidden="true" />
      <p className="mt-4 text-[20px] font-semibold text-white">{title}</p>
      {text && <p className="mt-1.5 text-[15px] text-ink-muted max-w-sm">{text}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-[15px] text-ink-muted" role="status">
      <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
      {label}
    </div>
  );
}

// ---------------------------------------------------------------- buttons

export const iconButton =
  'w-9 h-9 rounded-full flex items-center justify-center text-ios-blue hover:bg-white/[0.08] transition-colors';
export const secondaryButton =
  'h-9 px-4 rounded-full bg-ios-fill text-[15px] font-medium text-ios-blue hover:bg-white/[0.16] transition-colors disabled:opacity-40';
export const ghostButton =
  'text-[15px] text-ios-blue hover:opacity-70 px-2 h-9 transition-opacity';
export const primaryButton = 'btn-primary h-9 px-4 text-[15px] flex items-center gap-1.5';
