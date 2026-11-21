// OSOBA 3 – Outbox: statusy wysyłek, symulacja awarii kanałów, ponawianie i podgląd treści.
import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  ExternalLink,
  Inbox,
  Mail,
  MessageSquare,
  Phone,
  RefreshCw,
  RotateCcw,
  WifiOff,
} from 'lucide-react';
import { api } from '../shared/api';
import type { Delivery } from '../shared/types';
import type { Channel } from '../rules/ruleTypes';
import { errorMessage } from '../rules/rulesApi';
import { parseUtc, timeAgo } from '../alerts/AlertCard';

interface ChannelStatus {
  channel: Channel;
  provider: string;
  simulated_down: boolean;
  error_message: string | null;
  updated_at: string | null;
}

interface DeliveryStats {
  total: number;
  sent: number;
  pending: number;
  failed: number;
  exhausted: number;
  channels: ChannelStatus[];
}

type StatusFilter = 'all' | 'pending' | 'sent' | 'failed';
type ChannelFilter = 'all' | Channel;

const CHANNEL_META: Record<Channel, { label: string; icon: typeof Mail }> = {
  email: { label: 'Email', icon: Mail },
  sms: { label: 'SMS', icon: MessageSquare },
  phone: { label: 'Phone', icon: Phone },
  ui: { label: 'UI', icon: Bell },
};

function ChannelBadge({ channel }: { channel: Channel }) {
  const meta = CHANNEL_META[channel] ?? { label: channel, icon: Bell };
  const Icon = meta.icon;
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-slate-800 border border-slate-700 text-xs font-medium text-slate-200">
      <Icon className="w-3.5 h-3.5 text-amber-400" />
      {meta.label}
    </span>
  );
}

function StatusPill({ status, exhausted }: { status: Delivery['status']; exhausted?: boolean }) {
  if (status === 'sent') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
        <CheckCircle2 className="w-3 h-3" />
        Sent
      </span>
    );
  }
  if (status === 'failed') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
        <AlertTriangle className="w-3 h-3" />
        {exhausted ? 'Failed (max retries)' : 'Failed'}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
      <Clock className="w-3 h-3" />
      Pending
    </span>
  );
}

export default function OutboxPage() {
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [stats, setStats] = useState<DeliveryStats | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [channelFilter, setChannelFilter] = useState<ChannelFilter>('all');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [retryingAll, setRetryingAll] = useState(false);
  const [togglingChannel, setTogglingChannel] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  const flash = (msg: string) => {
    setNotice(msg);
    window.setTimeout(() => setNotice(null), 3500);
  };

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: '150' });
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (channelFilter !== 'all') params.set('channel', channelFilter);

      const [rows, st] = await Promise.all([
        api<Delivery[]>(`/deliveries?${params.toString()}`),
        api<DeliveryStats>('/deliveries/stats'),
      ]);
      setDeliveries(rows);
      setStats(st);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [statusFilter, channelFilter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => {
      load();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, load]);

  const handleToggleOutage = async (ch: ChannelStatus) => {
    setTogglingChannel(ch.channel);
    setError(null);
    try {
      const nextDown = !ch.simulated_down;
      await api(`/deliveries/channels/${encodeURIComponent(ch.channel)}/outage`, {
        method: 'POST',
        body: JSON.stringify({
          down: nextDown,
          error_message: nextDown ? `Simulated ${ch.channel.toUpperCase()} provider outage` : null,
        }),
      });
      await load();
      flash(
        nextDown
          ? `${CHANNEL_META[ch.channel]?.label ?? ch.channel} outage simulation enabled.`
          : `${CHANNEL_META[ch.channel]?.label ?? ch.channel} restored — queued deliveries flushed.`,
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setTogglingChannel(null);
    }
  };

  const handleRetryOne = async (d: Delivery) => {
    setBusyId(d.id);
    setError(null);
    try {
      await api(`/deliveries/${d.id}/retry`, { method: 'POST' });
      await load();
      flash(`Retried delivery #${d.id}.`);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusyId(null);
    }
  };

  const handleRetryAllFailed = async () => {
    setRetryingAll(true);
    setError(null);
    try {
      const res = await api<{ reset: number; sent: number; failed: number }>('/deliveries/retry-failed', {
        method: 'POST',
      });
      await load();
      flash(`Retried ${res.reset} failed deliveries (${res.sent} sent, ${res.failed} failed).`);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRetryingAll(false);
    }
  };

  const channels = stats?.channels ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <Inbox className="w-6 h-6 text-amber-400" />
            Outbox &amp; Delivery
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Audit notification deliveries per channel, inspect formatted payloads, and test channel outage retries.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-slate-700 bg-slate-900 accent-amber-500"
            />
            Auto-refresh (3s)
          </label>

          <button
            type="button"
            onClick={load}
            className="flex items-center gap-1.5 text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg border border-slate-700 transition"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>

          {(stats?.failed ?? 0) > 0 && (
            <button
              type="button"
              disabled={retryingAll}
              onClick={handleRetryAllFailed}
              className="flex items-center gap-1.5 text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-slate-950 px-3.5 py-1.5 rounded-lg disabled:opacity-50 transition"
            >
              <RotateCcw className={`w-4 h-4 ${retryingAll ? 'animate-spin' : ''}`} />
              Retry All Failed ({stats?.failed})
            </button>
          )}
        </div>
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <div className="text-xs text-slate-400">Total Deliveries</div>
          <div className="text-2xl font-bold text-white mt-1">{stats?.total ?? 0}</div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <div className="text-xs text-slate-400">Sent</div>
          <div className="text-2xl font-bold text-emerald-400 mt-1">{stats?.sent ?? 0}</div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <div className="text-xs text-slate-400">Pending</div>
          <div className="text-2xl font-bold text-amber-400 mt-1">{stats?.pending ?? 0}</div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <div className="text-xs text-slate-400">Failed</div>
          <div className="text-2xl font-bold text-rose-400 mt-1">{stats?.failed ?? 0}</div>
        </div>
      </div>

      {/* Channel Health & Outage Simulator */}
      <section className="space-y-2.5">
        <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Channel Health &amp; Outage Simulator
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {channels.map((ch) => {
            const meta = CHANNEL_META[ch.channel] ?? { label: ch.channel, icon: Bell };
            const Icon = meta.icon;
            const busy = togglingChannel === ch.channel;
            return (
              <div
                key={ch.channel}
                className={`p-4 rounded-xl border transition flex flex-col justify-between gap-3 ${
                  ch.simulated_down
                    ? 'bg-rose-500/10 border-rose-500/40'
                    : 'bg-slate-900 border-slate-800'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2 text-sm font-bold text-white">
                      <Icon className="w-4 h-4 text-amber-400" />
                      {meta.label}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-0.5">{ch.provider}</div>
                  </div>
                  {ch.simulated_down ? (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                      <WifiOff className="w-3 h-3" />
                      Simulated Outage
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                      Operational
                    </span>
                  )}
                </div>

                {ch.channel !== 'ui' && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleToggleOutage(ch)}
                    className={`w-full px-3 py-1.5 rounded-lg text-xs font-semibold border transition disabled:opacity-50 ${
                      ch.simulated_down
                        ? 'bg-emerald-500/15 hover:bg-emerald-500/25 border-emerald-500/40 text-emerald-300'
                        : 'bg-slate-800 hover:bg-rose-500/15 border-slate-700 hover:border-rose-500/40 text-slate-300 hover:text-rose-300'
                    }`}
                  >
                    {busy ? 'Updating...' : ch.simulated_down ? 'Restore Channel' : 'Simulate Outage'}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {error && (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {notice && (
        <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{notice}</span>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-1.5">
          {(['all', 'pending', 'sent', 'failed'] as StatusFilter[]).map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold capitalize border transition ${
                statusFilter === st
                  ? 'bg-amber-500/20 border-amber-500 text-amber-300'
                  : 'border-slate-800 bg-slate-900 text-slate-400 hover:text-white'
              }`}
            >
              {st}
            </button>
          ))}
        </div>

        <select
          value={channelFilter}
          onChange={(e) => setChannelFilter(e.target.value as ChannelFilter)}
          aria-label="Channel filter"
          className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-amber-500"
        >
          <option value="all">All channels</option>
          <option value="email">Email</option>
          <option value="sms">SMS</option>
          <option value="phone">Phone</option>
          <option value="ui">UI</option>
        </select>
      </div>

      {/* Deliveries List */}
      {deliveries.length === 0 ? (
        <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
          <p className="text-slate-400">No deliveries match this filter.</p>
          <p className="text-xs text-slate-600 mt-1">
            Trigger an event on the Sources tab to see notifications flow through the Outbox.
          </p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {deliveries.map((d) => {
            const isExpanded = Boolean(expanded[d.id]);
            const maxAttempts = d.max_attempts ?? 5;
            const whenIso = d.sent_at ?? d.created_at;
            return (
              <div
                key={d.id}
                className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden"
              >
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => setExpanded((prev) => ({ ...prev, [d.id]: !isExpanded }))}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setExpanded((prev) => ({ ...prev, [d.id]: !isExpanded }));
                    }
                  }}
                  className="px-4 py-3.5 flex flex-wrap items-center justify-between gap-3 cursor-pointer hover:bg-slate-800/40 transition"
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" />
                    )}

                    <StatusPill status={d.status} exhausted={d.exhausted} />
                    <ChannelBadge channel={d.channel} />

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-white">
                          {d.person_name ?? (d.person_id ? `Person #${d.person_id}` : 'Team feed')}
                        </span>
                        <span className="text-xs font-mono text-slate-400 truncate">
                          {d.to ?? 'Live UI'}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 mt-0.5">
                        <a
                          href={d.alert_link ?? `/#alerts/${d.alert_id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 text-amber-300 hover:underline truncate max-w-md"
                        >
                          <span>#{d.alert_id}: {d.alert_title ?? 'View alert'}</span>
                          <ExternalLink className="w-3 h-3 shrink-0" />
                        </a>
                        {d.alert_team && <span className="text-slate-500">· {d.alert_team}</span>}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0">
                    <span
                      className="text-xs font-mono text-slate-400 bg-slate-950 border border-slate-800 px-2 py-0.5 rounded"
                      title="Delivery attempts"
                    >
                      {d.attempts}/{maxAttempts}
                    </span>

                    <span
                      className="text-xs text-slate-500"
                      title={whenIso ? parseUtc(whenIso).toLocaleString() : ''}
                    >
                      {whenIso ? timeAgo(whenIso) : ''}
                    </span>

                    {d.status === 'failed' && (
                      <button
                        type="button"
                        disabled={busyId === d.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRetryOne(d);
                        }}
                        className="px-2.5 py-1 rounded-lg text-xs font-semibold border border-amber-500/40 text-amber-300 hover:bg-amber-500/10 disabled:opacity-50 flex items-center gap-1 transition"
                      >
                        <RotateCcw className={`w-3.5 h-3.5 ${busyId === d.id ? 'animate-spin' : ''}`} />
                        Retry
                      </button>
                    )}
                  </div>
                </div>

                {d.last_error && (
                  <div className="mx-4 mb-3 p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span>
                      {d.last_error}
                      {d.next_retry_at && !d.exhausted && (
                        <span className="text-rose-200/70 ml-2">
                          (next auto-retry: {parseUtc(d.next_retry_at).toLocaleTimeString()})
                        </span>
                      )}
                    </span>
                  </div>
                )}

                {isExpanded && d.message_preview && (
                  <div className="px-4 pb-4 pt-2 border-t border-slate-800/80 space-y-2">
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                      Rendered {CHANNEL_META[d.channel]?.label ?? d.channel} Payload
                    </div>
                    {d.message_preview.subject && (
                      <div className="text-xs text-slate-200">
                        <span className="text-slate-500 mr-2">Subject:</span>
                        <span className="font-semibold">{d.message_preview.subject}</span>
                      </div>
                    )}
                    <pre className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs font-mono text-emerald-300 whitespace-pre-wrap break-words">
                      {d.message_preview.body ?? d.message_preview.script ?? ''}
                    </pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
