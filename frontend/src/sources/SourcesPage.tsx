import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Plus,
  Download,
  RefreshCw,
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
  CheckCircle2,
  Terminal,
  Search,
  ChevronDown,
  ChevronRight,
  X,
} from 'lucide-react';
import { api } from '../shared/api';
import type { Source, SourceKind } from '../shared/types';
import type {
  ConnectorTypeSpec,
  EventRecord,
  ExportSpecResult,
  SimulatorPreset,
  SourceTypesResponse,
  TestConnectionResult,
} from './sourceTypes';
import SourceSpecModal from './SourceSpecModal';
import SimulateModal from './SimulateModal';

function SourceKindBadge({ kind, label }: { kind: SourceKind; label?: string }) {
  const iconProps = 'w-3.5 h-3.5';
  const icon = (() => {
    switch (kind) {
      case 'webhook':
        return <Webhook className={iconProps} />;
      case 'polled_api':
        return <Globe className={iconProps} />;
      case 'sse':
        return <Radio className={iconProps} />;
      case 'logfile':
        return <FileText className={iconProps} />;
      case 'kafka':
        return <Layers className={iconProps} />;
      case 'rabbitmq':
        return <Mail className={iconProps} />;
      default:
        return <Sliders className={iconProps} />;
    }
  })();

  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-slate-800 border border-slate-700 text-xs font-medium text-slate-200">
      <span className="text-amber-400">{icon}</span>
      {label || kind}
    </span>
  );
}

function StatusPill({ status, workerRunning }: { status: Source['status']; workerRunning?: boolean }) {
  if (status === 'error') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
        Error
      </span>
    );
  }
  if (status === 'paused') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">
        <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
        Paused
      </span>
    );
  }
  if (status === 'simulating') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        Simulating{workerRunning ? ' (live)' : ''}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
      Active
    </span>
  );
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
  const [testResults, setTestResults] = useState<Record<number, TestConnectionResult>>({});
  const [testingId, setTestingId] = useState<number | null>(null);

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

  const handleTestConnection = async (src: Source) => {
    setTestingId(src.id);
    try {
      const res = await api<TestConnectionResult>(`/sources/${src.id}/test-connection`, {
        method: 'POST',
      });
      setTestResults((prev) => ({ ...prev, [src.id]: res }));
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [src.id]: {
          ok: false,
          mode: src.kind,
          message: err instanceof Error ? err.message : 'Connection test failed',
        },
      }));
    } finally {
      setTestingId(null);
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
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
            <Plug className="w-6 h-6 text-amber-400" />
            Universal Log &amp; Event Sources
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Connect any webhook, polled REST API, SSE stream, tailed log file, Kafka topic, RabbitMQ queue, or custom spec — and simulate any source on demand.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setEditingSource(null);
              setShowSpecModal(true);
            }}
            className="px-4 py-2 rounded-lg text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-slate-950 flex items-center gap-1.5 shadow transition"
          >
            <Plus className="w-4 h-4" />
            Add Source
          </button>
        </div>
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <div className="text-xs text-slate-400">Configured Sources</div>
          <div className="text-2xl font-bold text-white mt-1">{sources.length}</div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <div className="text-xs text-slate-400">Enabled / Active</div>
          <div className="text-2xl font-bold text-emerald-400 mt-1">{activeCount}</div>
        </div>
        <div className="p-4 rounded-xl bg-slate-900 border border-slate-800">
          <div className="text-xs text-slate-400">Total Events Ingested</div>
          <div className="text-2xl font-bold text-amber-400 mt-1">{totalEventsCount}</div>
        </div>
      </div>

      {/* Sub-navigation Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setActiveSubTab('sources')}
            className={`px-3.5 py-1.5 rounded-lg text-sm font-medium flex items-center gap-1.5 transition ${
              activeSubTab === 'sources'
                ? 'bg-slate-800 text-white'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Plug className="w-4 h-4" />
            Sources ({sources.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveSubTab('events')}
            className={`px-3.5 py-1.5 rounded-lg text-sm font-medium flex items-center gap-1.5 transition ${
              activeSubTab === 'events'
                ? 'bg-slate-800 text-white'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Activity className="w-4 h-4" />
            Live Event Inspector
          </button>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-slate-700 bg-slate-900 text-amber-500"
            />
            Auto-refresh (4s)
          </label>
          <button
            type="button"
            onClick={() => {
              loadSourcesAndMeta();
              loadEvents();
            }}
            className="p-1.5 rounded-lg bg-slate-900 border border-slate-700 text-slate-400 hover:text-white transition"
            title="Refresh now"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
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
          <div className="py-12 text-center text-slate-400 text-sm">Loading sources...</div>
        ) : sources.length === 0 ? (
          <div className="p-12 rounded-2xl border border-dashed border-slate-700 text-center space-y-3">
            <Plug className="w-8 h-8 text-slate-500 mx-auto" />
            <div className="text-white font-semibold">No sources configured yet</div>
            <p className="text-xs text-slate-400 max-w-md mx-auto">
              Add a webhook, polled REST API, SSE stream, log file tailer, Kafka topic, or RabbitMQ queue to begin ingesting events.
            </p>
            <button
              type="button"
              onClick={() => {
                setEditingSource(null);
                setShowSpecModal(true);
              }}
              className="px-4 py-2 rounded-lg text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-slate-950"
            >
              Add First Source
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {sources.map((src) => {
              const spec = typeMap[src.kind];
              const fullIngestUrl = `${origin}/api/ingest/${src.key}`;
              const sampleJson = JSON.stringify(
                src.sample_event || { type: 'TEST_EVENT', service: src.name, severity: 'warning' }
              );
              const curlCmd = `curl -X POST "${fullIngestUrl}" \\\n  -H "Content-Type: application/json" \\\n  -d '${sampleJson}'`;
              const testRes = testResults[src.id];

              return (
                <div
                  key={src.id}
                  className="p-5 rounded-2xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition space-y-4"
                >
                  {/* Top Row */}
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-bold text-white">{src.name}</h3>
                        <span className="text-xs text-slate-300 bg-slate-800 px-2 py-0.5 rounded">{src.team}</span>
                        <SourceKindBadge kind={src.kind} label={spec?.label} />
                        {spec && (
                          <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-400">
                            {spec.mode}
                          </span>
                        )}
                        <StatusPill status={src.status} workerRunning={src.worker_running} />
                      </div>
                      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                        <span>
                          Events: <strong className="text-amber-300">{src.events_count || 0}</strong>
                        </span>
                        {src.last_event_at && (
                          <>
                            <span>•</span>
                            <span>
                              Last event: {new Date(src.last_event_at + 'Z').toLocaleTimeString()}
                            </span>
                          </>
                        )}
                        {Boolean(src.config?.root_path) && (
                          <>
                            <span>•</span>
                            <span className="font-mono text-[11px] text-slate-300">
                              unwrap: {String(src.config.root_path)}
                            </span>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex flex-wrap items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => setSimulatingSource(src)}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30 flex items-center gap-1.5 transition"
                      >
                        <Play className="w-3.5 h-3.5" />
                        Simulate
                      </button>

                      <button
                        type="button"
                        disabled={testingId === src.id}
                        onClick={() => handleTestConnection(src)}
                        className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
                      >
                        {testingId === src.id ? 'Testing...' : 'Test'}
                      </button>

                      <button
                        type="button"
                        onClick={() => handleToggle(src)}
                        title={src.enabled ? 'Pause source' : 'Enable source'}
                        className={`p-1.5 rounded-lg border transition ${
                          src.enabled
                            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/20'
                            : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
                        }`}
                      >
                        <Power className="w-4 h-4" />
                      </button>

                      <button
                        type="button"
                        onClick={() => handleExport(src, 'yaml')}
                        title="Export YAML Spec"
                        className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 transition"
                      >
                        <Download className="w-4 h-4" />
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          const copy: Source = {
                            ...src,
                            id: 0,
                            name: `${src.name} (Copy)`,
                            key: `${src.key}-copy`,
                          };
                          setEditingSource(copy);
                          setShowSpecModal(true);
                        }}
                        title="Duplicate source (create copy)"
                        className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-amber-400 transition"
                      >
                        <Copy className="w-4 h-4" />
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setEditingSource(src);
                          setShowSpecModal(true);
                        }}
                        title="Edit specification"
                        className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 transition"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>

                      <button
                        type="button"
                        onClick={() => handleDelete(src)}
                        title="Delete source"
                        className="p-1.5 rounded-lg bg-slate-800 hover:bg-rose-500/20 border border-slate-700 text-slate-400 hover:text-rose-400 transition"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Error Banner */}
                  {src.last_error && (
                    <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <span>{src.last_error}</span>
                    </div>
                  )}

                  {/* Connection Test Result */}
                  {testRes && (
                    <div
                      className={`p-2.5 rounded-lg border text-xs flex items-center justify-between gap-2 ${
                        testRes.ok
                          ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                          : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {testRes.ok ? (
                          <CheckCircle2 className="w-4 h-4 shrink-0" />
                        ) : (
                          <AlertTriangle className="w-4 h-4 shrink-0" />
                        )}
                        <span>{testRes.message}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() =>
                          setTestResults((prev) => {
                            const next = { ...prev };
                            delete next[src.id];
                            return next;
                          })
                        }
                        className="text-slate-400 hover:text-white"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}

                  {/* Push Ingest Endpoint + Curl */}
                  <div className="flex flex-wrap items-center justify-between gap-2 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-mono">
                        POST
                      </span>
                      <code className="text-xs font-mono text-slate-200 truncate">
                        {fullIngestUrl}
                      </code>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        type="button"
                        onClick={() => copyText(`url-${src.id}`, fullIngestUrl)}
                        className="px-2 py-1 rounded-md bg-slate-900 hover:bg-slate-800 border border-slate-700 text-[11px] text-slate-300 flex items-center gap-1"
                      >
                        {copiedId === `url-${src.id}` ? (
                          <>
                            <Check className="w-3 h-3 text-emerald-400" />
                            Copied
                          </>
                        ) : (
                          <>
                            <Copy className="w-3 h-3" />
                            Copy URL
                          </>
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => setOpenCurlId(openCurlId === src.id ? null : src.id)}
                        className="px-2 py-1 rounded-md bg-slate-900 hover:bg-slate-800 border border-slate-700 text-[11px] text-slate-300 flex items-center gap-1"
                      >
                        <Terminal className="w-3 h-3" />
                        cURL
                      </button>
                    </div>
                  </div>

                  {openCurlId === src.id && (
                    <div className="relative">
                      <pre className="bg-slate-950 border border-slate-800 rounded-xl p-3 text-[11px] font-mono text-emerald-300 overflow-x-auto">
                        {curlCmd}
                      </pre>
                      <button
                        type="button"
                        onClick={() => copyText(`curl-${src.id}`, curlCmd)}
                        className="absolute top-2 right-2 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[11px] text-slate-200"
                      >
                        {copiedId === `curl-${src.id}` ? 'Copied!' : 'Copy'}
                      </button>
                    </div>
                  )}

                  {/* Detected Schema Fields Preview */}
                  {src.detected_fields && src.detected_fields.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] text-slate-500 mr-1">Detected fields:</span>
                      {src.detected_fields.slice(0, 10).map((f) => (
                        <span
                          key={f.path}
                          className="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-300"
                        >
                          <span className="text-amber-400">{f.path}</span>
                          <span className="text-slate-500 ml-1">:{f.type}</span>
                        </span>
                      ))}
                      {src.detected_fields.length > 10 && (
                        <span className="text-[11px] text-slate-500">
                          +{src.detected_fields.length - 10} more
                        </span>
                      )}
                    </div>
                  )}
                </div>
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
              className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
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
                className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
              />
            </div>
          </div>

          {filteredEvents.length === 0 ? (
            <div className="p-10 rounded-2xl border border-dashed border-slate-800 text-center text-sm text-slate-400">
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
                    className="rounded-xl bg-slate-900 border border-slate-800 overflow-hidden"
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
                          <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" />
                        )}
                        <span className="text-xs font-mono text-slate-500 shrink-0">
                          #{ev.id}
                        </span>
                        {ev.source && (
                          <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-800 text-amber-300 shrink-0">
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
                        <pre className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs font-mono text-emerald-300 overflow-x-auto">
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
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-white">
                  Export Source Specification — {exportModal.filename}
                </h3>
                <p className="text-xs text-slate-400">
                  Config-as-Code export (secrets are masked).
                </p>
              </div>
              <button
                type="button"
                onClick={() => setExportModal(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-6">
              <pre className="bg-slate-950 border border-slate-800 rounded-xl p-4 text-xs font-mono text-emerald-300 overflow-x-auto max-h-96">
                {exportModal.content}
              </pre>
            </div>
            <div className="px-6 py-4 border-t border-slate-800 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => copyText('export-spec', exportModal.content)}
                className="px-4 py-2 rounded-lg text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-slate-950 flex items-center gap-1.5"
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
