import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Plus,
  Download,
  Copy,
  Check,
  Play,
  Power,
  Pencil,
  Trash2,
  Plug,
  Activity,
  Webhook,
  Globe,
  Radio,
  FileText,
  Layers,
  Mail,
  Sliders,
  AlertTriangle,
  Terminal,
  Search,
  ChevronDown,
  ChevronRight,
  X,
} from 'lucide-react';
import { PageHeader, Row, Toggle } from '../shared/ui';
import { api } from '../shared/api';
import type { Source, SourceKind } from '../shared/types';
import type {
  ConnectorTypeSpec,
  EventRecord,
  ExportSpecResult,
  SimulatorPreset,
  SourceTypesResponse,
} from './sourceTypes';
import SourceSpecModal from './SourceSpecModal';
import SimulateModal from './SimulateModal';

// Neutral gray rounded-square icon per source type (same quiet style as People avatars)
function SourceKindIcon({ kind }: { kind: SourceKind }) {
  const Icon = (() => {
    switch (kind) {
      case 'webhook': return Webhook;
      case 'polled_api': return Globe;
      case 'sse': return Radio;
      case 'logfile': return FileText;
      case 'kafka': return Layers;
      case 'rabbitmq': return Mail;
      default: return Sliders;
    }
  })();
  return (
    <span className="w-10 h-10 rounded-[10px] bg-gradient-to-b from-[#8e8e93] to-[#636366] flex items-center justify-center shrink-0" aria-hidden="true">
      <Icon className="w-5 h-5 text-white" strokeWidth={2} />
    </span>
  );
}

function StatusText({ status, workerRunning }: { status: Source['status']; workerRunning?: boolean }) {
  if (status === 'error') return <span className="text-ios-red">error</span>;
  if (status === 'paused') return <span>paused</span>;
  if (status === 'simulating') return <span className="text-ios-orange">simulating{workerRunning ? ', live' : ''}</span>;
  return <span className="text-ios-green">active</span>;
}

export default function SourcesPage() {
  const [activeSubTab, setActiveSubTab] = useState<'sources' | 'events'>('sources');
  const [sources, setSources] = useState<Source[]>([]);
  const [types, setTypes] = useState<ConnectorTypeSpec[]>([]);
  const [presets, setPresets] = useState<SimulatorPreset[]>([]);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modals
  const [showSpecModal, setShowSpecModal] = useState(false);
  const [editingSource, setEditingSource] = useState<Source | null>(null);
  const [simulatingSource, setSimulatingSource] = useState<Source | null>(null);
  const [exportModal, setExportModal] = useState<ExportSpecResult | null>(null);

  // Per-card UI state
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [openCurlId, setOpenCurlId] = useState<number | null>(null);

  // Event Inspector filters
  const [eventSourceFilter, setEventSourceFilter] = useState<string>('all');
  const [eventSearch, setEventSearch] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [expandedEvents, setExpandedEvents] = useState<Record<number, boolean>>({});

  const typeMap = useMemo(() => {
    const map: Record<string, ConnectorTypeSpec> = {};
    for (const t of types) map[t.kind] = t;
    return map;
  }, [types]);

  const loadSourcesAndMeta = useCallback(async () => {
    try {
      const [meta, srcList] = await Promise.all([
        api<SourceTypesResponse>('/sources/types'),
        api<Source[]>('/sources'),
      ]);
      setTypes(meta.types);
      setPresets(meta.presets);
      setSources(srcList);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sources');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadEvents = useCallback(async () => {
    try {
      const qs =
        eventSourceFilter !== 'all'
          ? `/events?limit=80&source_id=${encodeURIComponent(eventSourceFilter)}`
          : '/events?limit=80';
      const data = await api<EventRecord[]>(qs);
      setEvents(data);
    } catch {
      // Keep previous events visible on transient polling errors
    }
  }, [eventSourceFilter]);

  useEffect(() => {
    loadSourcesAndMeta();
  }, [loadSourcesAndMeta]);

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  // Auto-refresh sources & events every 4s when enabled
  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => {
      loadSourcesAndMeta();
      loadEvents();
    }, 4000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, loadSourcesAndMeta, loadEvents]);

  const copyText = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    window.setTimeout(() => setCopiedId(null), 1800);
  };

  const handleToggle = async (src: Source) => {
    try {
      await api(`/sources/${src.id}/toggle`, { method: 'PATCH' });
      await loadSourcesAndMeta();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle source');
    }
  };

  const handleDelete = async (src: Source) => {
    if (!window.confirm(`Delete source "${src.name}"? Existing event history will be preserved.`)) {
      return;
    }
    try {
      await api(`/sources/${src.id}`, { method: 'DELETE' });
      await loadSourcesAndMeta();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete source');
    }
  };

  const handleExport = async (src: Source, format: 'yaml' | 'json') => {
    try {
      const res = await api<ExportSpecResult>(`/sources/${src.id}/export?format=${format}`);
      setExportModal(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed');
    }
  };

  const totalEventsCount = useMemo(
    () => sources.reduce((acc, s) => acc + (s.events_count || 0), 0),
    [sources]
  );

  const activeCount = useMemo(
    () => sources.filter((s) => s.enabled).length,
    [sources]
  );

  const filteredEvents = useMemo(() => {
    const q = eventSearch.trim().toLowerCase();
    if (!q) return events;
    return events.filter((ev) => {
      const str = JSON.stringify(ev.payload).toLowerCase();
      const srcName = ev.source?.name?.toLowerCase() || '';
      return str.includes(q) || srcName.includes(q);
    });
  }, [events, eventSearch]);

  const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000';

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <PageHeader
        title="Sources"
        description="Connect webhooks, polled APIs, SSE streams, log files, Kafka topics, RabbitMQ queues or a custom spec, and simulate any of them on demand."
        actions={
          <button
            type="button"
            onClick={() => {
              setEditingSource(null);
              setShowSpecModal(true);
            }}
            className="btn-primary px-4 h-10 text-sm flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            Add source
          </button>
        }
      />

      {/* KPI Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="glass-card glass-card--static p-5">
          <div className="text-[13px] text-ink-muted">Configured sources</div>
          <div className="text-3xl font-semibold tracking-tight tabular-nums text-white mt-1">{sources.length}</div>
        </div>
        <div className="glass-card glass-card--static p-5">
          <div className="text-[13px] text-ink-muted">Turned on</div>
          <div className="text-3xl font-semibold tracking-tight tabular-nums text-emerald-300 mt-1">{activeCount}</div>
        </div>
        <div className="glass-card glass-card--static p-5">
          <div className="text-[13px] text-ink-muted">Events received</div>
          <div className="text-3xl font-semibold tracking-tight tabular-nums text-gs-gold mt-1">{totalEventsCount}</div>
        </div>
      </div>

      {/* Sub-navigation Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="glass-pill p-1 gap-1">
          <button
            type="button"
            onClick={() => setActiveSubTab('sources')}
            className={`px-3.5 h-8 rounded-full text-sm font-medium flex items-center gap-1.5 border transition-all duration-300 ${
              activeSubTab === 'sources'
                ? 'bg-white/[0.12] border-white/20 text-white shadow-[inset_0_1px_1px_rgba(255,255,255,0.14)]'
                : 'border-transparent text-ink-muted hover:text-white'
            }`}
          >
            <Plug className="w-4 h-4" />
            Sources ({sources.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveSubTab('events')}
            className={`px-3.5 h-8 rounded-full text-sm font-medium flex items-center gap-1.5 border transition-all duration-300 ${
              activeSubTab === 'events'
                ? 'bg-white/[0.12] border-white/20 text-white shadow-[inset_0_1px_1px_rgba(255,255,255,0.14)]'
                : 'border-transparent text-ink-muted hover:text-white'
            }`}
          >
            <Activity className="w-4 h-4" />
            Live Event Inspector
          </button>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-ink-muted cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded accent-amber-500"
            />
            Auto-refresh (4s)
          </label>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* TAB 1: Configured Sources */}
      {activeSubTab === 'sources' && (
        loading ? (
          <div className="py-12 text-center text-ink-muted text-sm">Loading sources...</div>
        ) : sources.length === 0 ? (
          <div className="p-12 rounded-2xl border border-dashed border-white/10 text-center space-y-3">
            <Plug className="w-8 h-8 text-slate-500 mx-auto" />
            <div className="text-white font-semibold">No sources configured yet</div>
            <p className="text-xs text-ink-muted max-w-md mx-auto">
              Add a webhook, polled REST API, SSE stream, log file tailer, Kafka topic, or RabbitMQ queue to begin ingesting events.
            </p>
            <button
              type="button"
              onClick={() => {
                setEditingSource(null);
                setShowSpecModal(true);
              }}
              className="btn-primary px-4 py-2 text-sm"
            >
              Add First Source
            </button>
          </div>
        ) : (
          <div className="grid gap-5 lg:grid-cols-2 items-start">
            {sources.map((src) => {
              const spec = typeMap[src.kind];
              const fullIngestUrl = `${origin}/api/ingest/${src.key}`;
              const sampleJson = JSON.stringify(
                src.sample_event || { type: 'TEST_EVENT', service: src.name, severity: 'warning' }
              );
              const curlCmd = `curl -X POST "${fullIngestUrl}" \\\n  -H "Content-Type: application/json" \\\n  -d '${sampleJson}'`;

              return (
                <article key={src.id} className={`ios-group transition-opacity ${src.enabled ? '' : 'opacity-60'}`}>
                  {/* header: type icon, name, status, on/off switch */}
                  <div className="ios-row py-3.5">
                    <SourceKindIcon kind={src.kind} />
                    <div className="flex-1 min-w-0">
                      <h3 className="text-[17px] font-semibold text-white leading-snug truncate">{src.name}</h3>
                      <p className="text-[13px] text-ink-muted truncate">
                        {spec?.label ?? src.kind}, <StatusText status={src.status} workerRunning={src.worker_running} />
                      </p>
                    </div>
                    <Toggle checked={src.enabled} onChange={() => handleToggle(src)}
                      label={src.enabled ? `Pause ${src.name}` : `Turn on ${src.name}`} />
                  </div>

                  <Row label="Team" value={<span className="text-white">{src.team}</span>} />
                  <Row label="Events received" value={<span className="tabular-nums">{src.events_count || 0}</span>} />
                  {src.last_event_at && (
                    <Row label="Last event" value={new Date(src.last_event_at + 'Z').toLocaleTimeString()} />
                  )}
                  {spec && <Row label="Delivery" value={spec.mode === 'push' ? 'Pushed to us' : spec.mode === 'pull' ? 'We fetch it' : spec.mode} />}
                  {Boolean(src.config?.root_path) && (
                    <Row label="Unwraps" value={<code className="font-mono text-[13px]">{String(src.config.root_path)}</code>} />
                  )}

                  {src.last_error && (
                    <div className="ios-row items-start text-[15px] text-ios-red">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <span className="flex-1">{src.last_error}</span>
                    </div>
                  )}

                  {/* push endpoint */}
                  <div className="ios-row flex-col items-stretch gap-2">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-[15px] text-white">Send events to</span>
                      <div className="flex items-center gap-3 text-[15px]">
                        <button type="button" onClick={() => copyText(`url-${src.id}`, fullIngestUrl)}
                          className="text-ios-blue hover:opacity-70 inline-flex items-center gap-1">
                          {copiedId === `url-${src.id}` ? <><Check className="w-4 h-4" />Copied</> : 'Copy URL'}
                        </button>
                        <button type="button" onClick={() => setOpenCurlId(openCurlId === src.id ? null : src.id)}
                          className="text-ios-blue hover:opacity-70">
                          {openCurlId === src.id ? 'Hide cURL' : 'cURL'}
                        </button>
                      </div>
                    </div>
                    <code className="block text-[13px] font-mono text-ink-muted truncate">POST {fullIngestUrl}</code>
                    {openCurlId === src.id && (
                      <div className="relative">
                        <pre className="surface-well p-3 pr-16 text-[12px] font-mono text-white overflow-x-auto">{curlCmd}</pre>
                        <button type="button" onClick={() => copyText(`curl-${src.id}`, curlCmd)}
                          className="absolute top-2 right-3 text-[13px] text-ios-blue hover:opacity-70">
                          {copiedId === `curl-${src.id}` ? 'Copied' : 'Copy'}
                        </button>
                      </div>
                    )}
                  </div>

                  {/* detected fields */}
                  {src.detected_fields && src.detected_fields.length > 0 && (
                    <div className="ios-row flex-col items-stretch gap-2">
                      <span className="text-[15px] text-white">Fields found in events</span>
                      <div className="flex flex-wrap gap-1.5">
                        {src.detected_fields.slice(0, 10).map((f) => (
                          <span key={f.path} className="glass-pill px-2.5 py-0.5 text-[12px] font-mono text-white">
                            {f.path}<span className="text-ink-muted">{f.type}</span>
                          </span>
                        ))}
                        {src.detected_fields.length > 10 && (
                          <span className="text-[13px] text-ink-muted self-center">+{src.detected_fields.length - 10} more</span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* actions */}
                  <div className="ios-row flex-wrap gap-x-5 gap-y-2 text-[15px]">
                    <button type="button" onClick={() => setSimulatingSource(src)} className="text-ios-blue hover:opacity-70">Simulate</button>
                    <button type="button" onClick={() => handleExport(src, 'yaml')} className="text-ios-blue hover:opacity-70">Export</button>
                    <button type="button" onClick={() => { setEditingSource(src); setShowSpecModal(true); }}
                      className="text-ios-blue hover:opacity-70">Edit</button>
                    <button type="button" onClick={() => handleDelete(src)} className="ml-auto text-ios-red hover:opacity-70">Delete</button>
                  </div>
                </article>
              );
            })}
          </div>
        )
      )}

      {/* TAB 2: Live Event Inspector */}
      {activeSubTab === 'events' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={eventSourceFilter}
              onChange={(e) => setEventSourceFilter(e.target.value)}
              className="field px-3 py-2 text-sm"
            >
              <option value="all">All Sources</option>
              {sources.map((s) => (
                <option key={s.id} value={String(s.id)}>
                  {s.name} ({s.kind})
                </option>
              ))}
            </select>

            <div className="relative flex-1 min-w-[220px]">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                value={eventSearch}
                onChange={(e) => setEventSearch(e.target.value)}
                placeholder="Filter events by payload text, field, or source..."
                className="field w-full pl-9 pr-3 py-2 text-sm"
              />
            </div>
          </div>

          {filteredEvents.length === 0 ? (
            <div className="p-10 rounded-2xl border border-dashed border-white/[0.08] text-center text-sm text-ink-muted">
              No events ingested yet. Click <strong className="text-amber-400">Simulate</strong> on any source or POST to <code className="text-slate-200">/api/ingest/&#123;key&#125;</code>.
            </div>
          ) : (
            <div className="space-y-2">
              {filteredEvents.map((ev) => {
                const expanded = Boolean(expandedEvents[ev.id]);
                const summaryPreview = JSON.stringify(ev.payload).slice(0, 140);
                return (
                  <div
                    key={ev.id}
                    className="glass-card glass-card--static overflow-hidden"
                  >
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedEvents((prev) => ({ ...prev, [ev.id]: !expanded }))
                      }
                      className="w-full px-4 py-3 flex items-center justify-between gap-3 text-left hover:bg-slate-800/40 transition"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        {expanded ? (
                          <ChevronDown className="w-4 h-4 text-ink-muted shrink-0" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-ink-muted shrink-0" />
                        )}
                        <span className="text-xs font-mono text-slate-500 shrink-0">
                          #{ev.id}
                        </span>
                        {ev.source && (
                          <span className="text-xs font-semibold px-2 py-0.5 rounded bg-white/[0.06] text-amber-300 shrink-0">
                            {ev.source.name}
                          </span>
                        )}
                        <span className="text-xs font-mono text-slate-300 truncate">
                          {summaryPreview}
                        </span>
                      </div>
                      <span className="text-[11px] text-slate-500 shrink-0 font-mono">
                        {ev.received_at
                          ? new Date(ev.received_at + 'Z').toLocaleTimeString()
                          : ''}
                      </span>
                    </button>

                    {expanded && (
                      <div className="px-4 pb-4 pt-1 border-t border-slate-800/70">
                        <pre className="surface-well p-3 text-xs font-mono text-emerald-300 overflow-x-auto">
                          {JSON.stringify(ev.payload, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Modals */}
      {showSpecModal && (
        <SourceSpecModal
          types={types}
          presets={presets}
          existing={editingSource}
          onClose={() => setShowSpecModal(false)}
          onSaved={() => {
            setShowSpecModal(false);
            loadSourcesAndMeta();
          }}
        />
      )}

      {simulatingSource && (
        <SimulateModal
          source={simulatingSource}
          presets={presets}
          onClose={() => setSimulatingSource(null)}
          onSimulated={() => {
            loadSourcesAndMeta();
            loadEvents();
          }}
        />
      )}

      {exportModal && (
        <div className="glass-scrim fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="glass-card glass-card--static w-full max-w-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-white/[0.08] flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-white">
                  Export Source Specification — {exportModal.filename}
                </h3>
                <p className="text-xs text-ink-muted">
                  Config-as-Code export (secrets are masked).
                </p>
              </div>
              <button
                type="button"
                onClick={() => setExportModal(null)}
                className="p-1.5 rounded-lg text-ink-muted hover:text-white hover:bg-white/[0.08]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-6">
              <pre className="surface-well p-4 text-xs font-mono text-emerald-300 overflow-x-auto max-h-96">
                {exportModal.content}
              </pre>
            </div>
            <div className="px-6 py-4 border-t border-white/[0.08] flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => copyText('export-spec', exportModal.content)}
                className="btn-primary px-4 py-2 text-sm flex items-center gap-1.5"
              >
                {copiedId === 'export-spec' ? (
                  <>
                    <Check className="w-4 h-4" />
                    Copied!
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    Copy Spec
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
