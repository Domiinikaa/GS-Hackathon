// Outbox: co, komu i jakim kanałem poszło, ze statusem i ponawianiem + przełączniki awarii + fałszywy telefon.
import { useEffect, useState } from 'react';
import { MessageSquare, RefreshCw } from 'lucide-react';
import { api } from '../shared/api';
import type { ChannelState, Delivery } from '../shared/types';
import { timeAgo } from '../alerts/AlertCard';
import FakePhone from './FakePhone';
import { CHANNEL_META, Notice, PageHeader, Row, RowIcon, Section, Toggle } from '../shared/ui';

const STATUS_TEXT: Record<Delivery['status'], string> = {
  pending: 'text-ink-muted',
  sending: 'text-ios-blue',
  sent: 'text-ios-green',
  failed: 'text-ios-orange',
  dead: 'text-ios-red',
};


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
            className="field h-[32px] px-3 text-[13px]">
            <option value="all">All statuses</option>
            <option value="pending">Pending</option>
            <option value="sent">Sent</option>
            <option value="failed">Failed (retrying)</option>
            <option value="dead">Dead</option>
          </select>
          <span className="flex items-center gap-1.5 text-xs text-ink-muted"><RefreshCw className="w-3.5 h-3.5" />Updates every 2 s</span>
        </>}
      />

      {error && <Notice tone="error">{error}</Notice>}

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-6 items-start">
        <div className="space-y-7 min-w-0">
          {/* Kanały i udawana awaria */}
          <Section title="Channels" footer="Turn on an outage to see messages fail and retry, then fall back to another channel.">
            {channels.map((c) => {
              const meta = CHANNEL_META[c.channel];
              const canToggle = c.channel === 'sms' || c.channel === 'phone';
              return (
                <Row key={c.channel}
                  icon={<RowIcon icon={meta?.icon ?? MessageSquare} color={c.down ? 'bg-ios-red' : (meta?.color ?? 'bg-ios-indigo')} />}
                  label={meta?.label ?? c.channel}
                  sublabel={c.down ? <span className="text-ios-red">Outage, messages are failing</span> : canToggle ? 'Working' : 'Working, sent by SMTP'}
                  accessory={canToggle
                    ? <Toggle checked={c.down} onChange={() => toggleOutage(c.channel, !c.down)}
                        label={c.down ? `Restore ${c.channel}` : `Simulate ${c.channel} outage`} />
                    : undefined} />
              );
            })}
          </Section>

          {/* Wysyłki */}
          <Section title={`Sent messages, ${deliveries.length}`}>
            {deliveries.map((d) => {
              const meta = CHANNEL_META[d.channel];
              return (
                <Row key={d.id}
                  icon={<RowIcon icon={meta?.icon ?? MessageSquare} color={meta?.color ?? 'bg-ios-indigo'} />}
                  label={<span className="font-semibold">{d.recipient_name ?? d.to ?? 'Unknown'}</span>}
                  sublabel={<span className="block truncate" title={d.body ?? ''}>{d.subject || d.body}</span>}
                  value={
                    <span className="flex flex-col items-end">
                      <span className={`text-[13px] font-semibold capitalize ${STATUS_TEXT[d.status] ?? ''}`}>{d.status}</span>
                      <span className="text-[13px] text-ink-muted whitespace-nowrap">{timeAgo(d.created_at)}{d.attempts > 1 && `, try ${d.attempts}`}</span>
                    </span>
                  } />
              );
            })}
            {deliveries.length === 0 && (
              <div className="ios-row flex-col items-start gap-0.5 py-4">
                <span className="text-[15px] text-white">Nothing sent yet</span>
                <span className="text-[13px] text-ink-muted">Send a test with <code className="font-mono">POST /api/deliveries/test</code> in API docs.</span>
              </div>
            )}
          </Section>
        </div>

        <FakePhone refreshKey={tick} />
      </div>
    </div>
  );
}
