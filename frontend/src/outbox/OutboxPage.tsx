// Outbox: co, komu i jakim kanałem poszło, ze statusem i ponawianiem + przełączniki awarii + fałszywy telefon.
import { useEffect, useState } from 'react';
import { Mail, MessageSquare, Phone, RefreshCw } from 'lucide-react';
import { api } from '../shared/api';
import type { ChannelState, Delivery } from '../shared/types';
import { timeAgo } from '../alerts/AlertCard';
import FakePhone from './FakePhone';

const STATUS_STYLE: Record<Delivery['status'], string> = {
  pending: 'bg-slate-700/50 text-slate-300',
  sending: 'bg-sky-500/15 text-sky-300',
  sent: 'bg-emerald-500/15 text-emerald-300',
  failed: 'bg-amber-500/15 text-amber-300',
  dead: 'bg-red-500/15 text-red-300',
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
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Outbox</h1>
          <p className="text-sm text-slate-400">Every notification we sent, by which channel, and whether it arrived.</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status"
            className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-white">
            <option value="all">All statuses</option>
            <option value="pending">Pending</option>
            <option value="sent">Sent</option>
            <option value="failed">Failed (retrying)</option>
            <option value="dead">Dead</option>
          </select>
          <span className="flex items-center gap-1 text-xs text-slate-500"><RefreshCw className="w-3.5 h-3.5" />auto 2s</span>
        </div>
      </div>

      {/* Kanały i udawana awaria */}
      <div className="flex flex-wrap gap-2">
        {channels.map((c) => {
          const Icon = CHANNEL_ICON[c.channel] ?? MessageSquare;
          const canToggle = c.channel === 'sms' || c.channel === 'phone';
          return (
            <div key={c.channel} className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm ${
              c.down ? 'border-red-500/40 bg-red-500/10 text-red-300' : 'border-slate-700 bg-slate-900 text-slate-300'}`}>
              <Icon className="w-4 h-4" />
              <span className="capitalize">{c.channel}</span>
              <span className={`w-2 h-2 rounded-full ${c.down ? 'bg-red-500' : 'bg-emerald-400'}`} />
              {canToggle ? (
                <button onClick={() => toggleOutage(c.channel, !c.down)}
                  className="text-xs underline decoration-dotted text-slate-400 hover:text-white">
                  {c.down ? 'restore' : 'simulate outage'}
                </button>
              ) : (
                <span className="text-xs text-slate-500" title="Inbox: http://localhost:8025">via SMTP</span>
              )}
            </div>
          );
        })}
      </div>

      {error && <div className="text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">{error}</div>}

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-6 items-start">
        {/* Tabela wysyłek */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-slate-400 border-b border-slate-800">
              <tr>
                <th className="text-left px-4 py-2.5">To</th>
                <th className="text-left px-4 py-2.5">Message</th>
                <th className="text-left px-4 py-2.5">Status</th>
                <th className="text-right px-4 py-2.5">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {deliveries.map((d) => {
                const Icon = CHANNEL_ICON[d.channel] ?? MessageSquare;
                return (
                  <tr key={d.id} className="align-top">
                    <td className="px-4 py-2.5 whitespace-nowrap">
                      <div className="flex items-center gap-2 text-slate-200"><Icon className="w-4 h-4 text-slate-400" />{d.recipient_name ?? '—'}</div>
                      <div className="text-xs text-slate-500 font-mono">{d.to}</div>
                    </td>
                    <td className="px-4 py-2.5 text-slate-300 max-w-xs">
                      <a href={`#alerts/${d.alert_id}`} className="text-xs text-slate-500 hover:underline">alert #{d.alert_id}</a>
                      <div className="truncate" title={d.body ?? ''}>{d.subject || d.body}</div>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded ${STATUS_STYLE[d.status] ?? ''}`}>{d.status}</span>
                      <div className="text-xs text-slate-500 mt-1">attempt {d.attempts}</div>
                      {d.last_error && d.status !== 'sent' && (
                        <div className="text-xs text-red-300/80 mt-0.5 max-w-[16rem] truncate" title={d.last_error}>{d.last_error}</div>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-slate-500 whitespace-nowrap">{timeAgo(d.created_at)}</td>
                  </tr>
                );
              })}
              {deliveries.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-10 text-center text-slate-500">
                  Nothing sent yet. Try <code className="text-amber-400">POST /api/deliveries/test</code> in /docs.
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
