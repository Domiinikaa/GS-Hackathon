// Outbox: co, komu i jakim kanałem poszło, ze statusem i ponawianiem + przełączniki awarii + fałszywy telefon.
import { useEffect, useState } from 'react';
import { Mail, MessageSquare, Phone, RefreshCw } from 'lucide-react';
import { api } from '../shared/api';
import type { ChannelState, Delivery } from '../shared/types';
import { timeAgo } from '../alerts/AlertCard';
import FakePhone from './FakePhone';
import { Notice, PageHeader, Toggle, cn } from '../shared/ui';

const STATUS_STYLE: Record<Delivery['status'], string> = {
  pending: 'bg-white/[0.06] text-slate-300 border-white/10',
  sending: 'bg-sky-500/10 text-sky-300 border-sky-500/30',
  sent: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
  failed: 'bg-amber-500/10 text-amber-300 border-amber-500/30',
  dead: 'bg-rose-500/10 text-rose-300 border-rose-500/30',
};

const CHANNEL_ICON = { email: Mail, sms: MessageSquare, phone: Phone, ui: MessageSquare } as const;

export default function OutboxPage() {
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [channels, setChannels] = useState<ChannelState[]>([]);
  const [status, setStatus] = useState<string>('all');
  const [tick, setTick] = useState(0);          // zwiększany co 2 s → odświeżenie tabeli i telefonu
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 2000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const query = status === 'all' ? '' : `?status=${status}`;
    Promise.all([api<Delivery[]>(`/deliveries${query}`), api<ChannelState[]>('/channels')])
      .then(([d, c]) => { setDeliveries(d); setChannels(c); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [tick, status]);

  async function toggleOutage(channel: string, down: boolean) {
    await api(`/channels/${channel}/outage`, { method: 'PUT', body: JSON.stringify({ down }) });
    setTick((t) => t + 1);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Outbox"
        description="Every notification we sent, by which channel, and whether it arrived."
        actions={<>
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"
            className="field h-9 px-3 text-sm !rounded-full">
            <option value="all">All statuses</option>
            <option value="pending">Pending</option>
            <option value="sent">Sent</option>
            <option value="failed">Failed (retrying)</option>
            <option value="dead">Dead</option>
          </select>
          <span className="flex items-center gap-1.5 text-xs text-ink-muted"><RefreshCw className="w-3.5 h-3.5" />Updates every 2 s</span>
        </>}
      />

      {/* Kanały i udawana awaria */}
      <div className="flex flex-wrap gap-2">
        {channels.map((c) => {
          const Icon = CHANNEL_ICON[c.channel] ?? MessageSquare;
          const canToggle = c.channel === 'sms' || c.channel === 'phone';
          return (
            <div key={c.channel} className={cn('glass-pill h-11 pl-3.5 pr-3 gap-2.5 text-sm transition-colors',
              c.down && '!border-rose-500/40 !bg-rose-500/10 text-rose-200')}>
              <Icon className={cn('w-4 h-4', c.down ? 'text-rose-300' : 'text-ink-muted')} />
              <span className="capitalize font-medium text-white">{c.channel}</span>
              <span className={cn('flex items-center gap-1.5 text-xs', c.down ? 'text-rose-300' : 'text-emerald-300')}>
                <span className={cn('w-1.5 h-1.5 rounded-full', c.down ? 'bg-rose-400' : 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]')} />
                {c.down ? 'Down' : 'Working'}
              </span>
              {canToggle ? (
                <span className="flex items-center gap-2 pl-2.5 ml-0.5 border-l border-white/10 text-xs text-ink-muted">
                  Outage
                  <Toggle checked={c.down} onChange={() => toggleOutage(c.channel, !c.down)}
                    label={c.down ? `Restore ${c.channel}` : `Simulate ${c.channel} outage`} className="scale-[0.82] origin-right" />
                </span>
              ) : (
                <span className="pl-2.5 ml-0.5 border-l border-white/10 text-xs text-ink-muted" title="Inbox: http://localhost:8025">Sent by SMTP</span>
              )}
            </div>
          );
        })}
      </div>

      {error && <Notice tone="error">{error}</Notice>}

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-6 items-start">
        {/* Tabela wysyłek */}
        <div className="glass-card glass-card--static overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-[13px] text-ink-muted border-b border-white/[0.08]">
              <tr>
                <th className="text-left font-medium px-5 py-3">To</th>
                <th className="text-left font-medium px-5 py-3">Message</th>
                <th className="text-left font-medium px-5 py-3">Status</th>
                <th className="text-right font-medium px-5 py-3">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.06]">
              {deliveries.map((d) => {
                const Icon = CHANNEL_ICON[d.channel] ?? MessageSquare;
                return (
                  <tr key={d.id} className="align-top hover:bg-white/[0.03] transition-colors">
                    <td className="px-5 py-3 whitespace-nowrap">
                      <div className="flex items-center gap-2 text-slate-200"><Icon className="w-4 h-4 text-ink-muted" />{d.recipient_name ?? '—'}</div>
                      <div className="text-xs text-slate-500 font-mono">{d.to}</div>
                    </td>
                    <td className="px-5 py-3 text-slate-300 max-w-xs">
                      <a href={`#alerts/${d.alert_id}`} className="text-xs text-slate-500 hover:underline">alert #{d.alert_id}</a>
                      <div className="truncate" title={d.body ?? ''}>{d.subject || d.body}</div>
                    </td>
                    <td className="px-5 py-3">
                      <span className={`inline-block text-xs font-medium capitalize px-2.5 py-0.5 rounded-full border ${STATUS_STYLE[d.status] ?? ''}`}>{d.status}</span>
                      <div className="text-xs text-slate-500 mt-1">Attempt {d.attempts}</div>
                      {d.last_error && d.status !== 'sent' && (
                        <div className="text-xs text-red-300/80 mt-0.5 max-w-[16rem] truncate" title={d.last_error}>{d.last_error}</div>
                      )}
                    </td>
                    <td className="px-5 py-3 text-right text-xs text-slate-500 whitespace-nowrap">{timeAgo(d.created_at)}</td>
                  </tr>
                );
              })}
              {deliveries.length === 0 && (
                <tr><td colSpan={4} className="px-5 py-14 text-center">
                  <p className="text-base font-semibold text-white">Nothing sent yet</p>
                  <p className="mt-1 text-sm text-ink-muted">Send a test with <code className="font-mono text-gs-gold">POST /api/deliveries/test</code> in API docs.</p>
                </td></tr>
              )}
            </tbody>
          </table>
        </div>

        <FakePhone refreshKey={tick} />
      </div>
    </div>
  );
}
