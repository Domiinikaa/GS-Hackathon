import { useEffect, useMemo, useState } from 'react';
import {
  X,
  Code2,
  Sliders,
  Play,
  CheckCircle2,
  AlertTriangle,
  Eye,
  EyeOff,
  Plus,
  Trash2,
  Sparkles,
  Webhook,
  Globe,
  Radio,
  FileText,
  Layers,
  Mail,
} from 'lucide-react';
import { api } from '../shared/api';
import type { Source, SourceKind } from '../shared/types';
import type {
  ConnectorTypeSpec,
  DryRunResult,
  FieldSpec,
  SimulatorPreset,
} from './sourceTypes';

interface SourceSpecModalProps {
  types: ConnectorTypeSpec[];
  presets: SimulatorPreset[];
  existing?: Source | null;
  initialRawMode?: boolean;
  onClose: () => void;
  onSaved: () => void;
}

const DEFAULT_LOG_REGEX =
  '^(?P<timestamp>\\S+)\\s+(?P<level>DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL)\\s+service=(?P<service>\\S+)\\s+(?:instrument=(?P<instrument>\\S+)\\s+)?(?:latency_ms=(?P<latency_ms>\\d+(?:\\.\\d+)?)\\s+)?(?:message=(?P<message>.+))?$';

function KindIcon({ icon, className = 'w-4 h-4' }: { icon: string; className?: string }) {
  switch (icon) {
    case 'webhook':
      return <Webhook className={className} />;
    case 'globe':
      return <Globe className={className} />;
    case 'radio':
      return <Radio className={className} />;
    case 'file-text':
      return <FileText className={className} />;
    case 'layers':
      return <Layers className={className} />;
    case 'mail':
      return <Mail className={className} />;
    default:
      return <Sliders className={className} />;
  }
}

function buildDefaultsForType(spec: ConnectorTypeSpec | undefined): Record<string, unknown> {
  const cfg: Record<string, unknown> = {
    parser: spec?.kind === 'logfile' ? 'key_value' : 'auto',
    root_path: '',
    field_aliases: {},
  };
  if (!spec) return cfg;
  for (const f of spec.config_schema) {
    if (f.default !== undefined && f.default !== null) {
      cfg[f.name] = f.default;
    }
  }
  return cfg;
}

export default function SourceSpecModal({
  types,
  presets,
  existing,
  initialRawMode = false,
  onClose,
  onSaved,
}: SourceSpecModalProps) {
  const isEditing = Boolean(existing);

  const [editorMode, setEditorMode] = useState<'form' | 'raw'>(
    initialRawMode && !isEditing ? 'raw' : 'form'
  );
  const [name, setName] = useState(existing?.name || '');
  const [kind, setKind] = useState<SourceKind>(existing?.kind || 'webhook');
  const [enabled, setEnabled] = useState<boolean>(existing ? existing.enabled : true);

  const activeSpec = useMemo(
    () => types.find((t) => t.kind === kind) || types[0],
    [types, kind]
  );

  const [config, setConfig] = useState<Record<string, unknown>>(() => {
    if (existing?.config) return { ...existing.config };
    return buildDefaultsForType(types.find((t) => t.kind === (existing?.kind || 'webhook')));
  });

  // Track JSON-typed config fields as raw strings while editing
  const [jsonTextMap, setJsonTextMap] = useState<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    const cfg = existing?.config || {};
    for (const [k, v] of Object.entries(cfg)) {
      if (k.endsWith('_json')) {
        out[k] = typeof v === 'string' ? v : JSON.stringify(v ?? {}, null, 2);
      }
    }
    return out;
  });

  // Field aliases state (Idea 5)
  const [aliases, setAliases] = useState<{ from: string; to: string }[]>(() => {
    const raw = existing?.config?.field_aliases;
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
      return Object.entries(raw as Record<string, string>).map(([from, to]) => ({ from, to }));
    }
    return [];
  });

  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});

  // Sample event & Dry-Run state (Idea 3)
  const [sampleText, setSampleText] = useState<string>(() => {
    if (existing?.sample_event) {
      return JSON.stringify(existing.sample_event, null, 2);
    }
    return '';
  });
  const [dryRunLoading, setDryRunLoading] = useState(false);
  const [dryRunError, setDryRunError] = useState<string | null>(null);
  const [dryRunResult, setDryRunResult] = useState<DryRunResult | null>(null);

  // Raw YAML / JSON Spec Mode (Idea 1)
  const [rawSpecText, setRawSpecText] = useState<string>(() => {
    if (initialRawMode && !existing) {
      return `name: rates-kafka-feed
team: Rates
kind: kafka
enabled: true
config:
  bootstrap_servers: localhost:9092
  topic: trade.rejections
  group_id: gs-alerting-consumer
  simulate: true
  sim_preset: trade_rejected
  sim_interval_s: 15
  parser: auto
  root_path: ""
  field_aliases: {}
`;
    }
    return '';
  });

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Sync defaults when user switches source kind on a new source
  const handleSelectKind = (nextKind: SourceKind) => {
    setKind(nextKind);
    const nextSpec = types.find((t) => t.kind === nextKind);
    if (!isEditing) {
      const defaults = buildDefaultsForType(nextSpec);
      setConfig(defaults);
      setJsonTextMap({});
    }
  };

  // Build final config object merging JSON textareas and field aliases
  const buildFinalConfig = (): Record<string, unknown> => {
    const out: Record<string, unknown> = { ...config };
    for (const [k, txt] of Object.entries(jsonTextMap)) {
      const trimmed = txt.trim();
      if (!trimmed) {
        out[k] = {};
      } else {
        try {
          out[k] = JSON.parse(trimmed);
        } catch {
          throw new Error(`Field '${k}' contains invalid JSON.`);
        }
      }
    }
    const aliasMap: Record<string, string> = {};
    for (const row of aliases) {
      if (row.from.trim() && row.to.trim()) {
        aliasMap[row.from.trim()] = row.to.trim();
      }
    }
    out.field_aliases = aliasMap;
    return out;
  };

  // Sync Form -> Raw JSON when switching to Raw mode
  useEffect(() => {
    if (editorMode === 'raw' && !rawSpecText.trim()) {
      try {
        const finalCfg = buildFinalConfig();
        let parsedSample: unknown = null;
        if (sampleText.trim()) {
          try {
            parsedSample = JSON.parse(sampleText);
          } catch {
            parsedSample = sampleText;
          }
        }
        const obj = {
          name: name || 'my-source',
          kind,
          enabled,
          config: finalCfg,
          sample_event: parsedSample,
        };
        setRawSpecText(JSON.stringify(obj, null, 2));
      } catch {
        // Ignore invalid intermediate JSON
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editorMode]);

  const handleApplyPreset = (presetId: string) => {
    const found = presets.find((p) => p.id === presetId);
    if (!found) return;
    if (typeof found.sample === 'string') {
      setSampleText(found.sample);
      if ((config.parser as string) === 'json') {
        setConfig((prev) => ({ ...prev, parser: 'key_value' }));
      }
    } else {
      setSampleText(JSON.stringify(found.sample, null, 2));
    }
  };

  const handleDryRun = async () => {
    if (!sampleText.trim()) {
      setDryRunError('Paste a sample JSON payload or raw log line (or pick a preset) first.');
      return;
    }
    setDryRunLoading(true);
    setDryRunError(null);
    setDryRunResult(null);
    try {
      const finalCfg = buildFinalConfig();
      const res = await api<DryRunResult>('/sources/dry-run', {
        method: 'POST',
        body: JSON.stringify({
          kind,
          config: finalCfg,
          raw_sample: sampleText,
        }),
      });
      setDryRunResult(res);
    } catch (err) {
      setDryRunError(err instanceof Error ? err.message : 'Dry-run failed');
    } finally {
      setDryRunLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      if (editorMode === 'raw' && !isEditing) {
        await api('/sources/import', {
          method: 'POST',
          body: JSON.stringify({ spec: rawSpecText }),
        });
        onSaved();
        return;
      }

      if (!name.trim()) {
        throw new Error('Source name is required.');
      }

      const finalCfg = buildFinalConfig();
      let sampleValue: unknown = null;
      if (sampleText.trim()) {
        try {
          sampleValue = JSON.parse(sampleText);
        } catch {
          sampleValue = sampleText;
        }
      }

      if (isEditing && existing) {
        await api(`/sources/${existing.id}`, {
          method: 'PUT',
          body: JSON.stringify({
            name: name.trim(),
            kind,
            enabled,
            config: finalCfg,
            sample_event: sampleValue,
          }),
        });
      } else {
        await api('/sources', {
          method: 'POST',
          body: JSON.stringify({
            name: name.trim(),
            team: 'All',
            kind,
            enabled,
            config: finalCfg,
            sample_event: sampleValue,
          }),
        });
      }
      onSaved();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save source');
    } finally {
      setSaving(false);
    }
  };

  const renderConfigField = (field: FieldSpec) => {
    const val = config[field.name];

    if (field.type === 'boolean') {
      const checked = Boolean(val ?? field.default);
      return (
        <div
          key={field.name}
          className="flex items-start justify-between gap-4 p-3 rounded-xl bg-slate-950/70 border border-slate-800"
        >
          <div>
            <div className="text-xs font-semibold text-slate-200">{field.label}</div>
            {field.description && (
              <div className="text-[11px] text-slate-400 mt-0.5">{field.description}</div>
            )}
          </div>
          <button
            type="button"
            onClick={() => setConfig((prev) => ({ ...prev, [field.name]: !checked }))}
            className={`relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors ${
              checked ? 'bg-amber-500' : 'bg-slate-700'
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-slate-950 transition-transform mt-0.5 ${
                checked ? 'translate-x-4' : 'translate-x-0.5'
              }`}
            />
          </button>
        </div>
      );
    }

    if (field.type === 'select') {
      return (
        <div key={field.name}>
          <label className="block text-xs font-medium text-slate-300 mb-1">
            {field.label}
          </label>
          <select
            value={String(val ?? field.default ?? '')}
            onChange={(e) => setConfig((prev) => ({ ...prev, [field.name]: e.target.value }))}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
          >
            {field.options.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
          {field.description && (
            <p className="text-[11px] text-slate-500 mt-1">{field.description}</p>
          )}
        </div>
      );
    }

    if (field.type === 'json') {
      const textVal =
        jsonTextMap[field.name] ??
        (typeof val === 'string' ? val : JSON.stringify(val ?? field.default ?? {}, null, 2));
      return (
        <div key={field.name} className="sm:col-span-2">
          <label className="block text-xs font-medium text-slate-300 mb-1">
            {field.label}
          </label>
          <textarea
            rows={3}
            value={textVal}
            placeholder={field.placeholder}
            onChange={(e) =>
              setJsonTextMap((prev) => ({ ...prev, [field.name]: e.target.value }))
            }
            className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-amber-500"
          />
          {field.description && (
            <p className="text-[11px] text-slate-500 mt-1">{field.description}</p>
          )}
        </div>
      );
    }

    if (field.type === 'secret') {
      const visible = Boolean(showSecrets[field.name]);
      return (
        <div key={field.name}>
          <label className="block text-xs font-medium text-slate-300 mb-1">
            {field.label}
          </label>
          <div className="relative">
            <input
              type={visible ? 'text' : 'password'}
              value={String(val ?? '')}
              placeholder={field.placeholder}
              onChange={(e) =>
                setConfig((prev) => ({ ...prev, [field.name]: e.target.value }))
              }
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 pr-9 text-sm text-white focus:outline-none focus:border-amber-500"
            />
            <button
              type="button"
              onClick={() =>
                setShowSecrets((prev) => ({ ...prev, [field.name]: !visible }))
              }
              className="absolute right-2.5 top-2.5 text-slate-400 hover:text-white"
            >
              {visible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {field.description && (
            <p className="text-[11px] text-slate-500 mt-1">{field.description}</p>
          )}
        </div>
      );
    }

    if (field.type === 'number') {
      return (
        <div key={field.name}>
          <label className="block text-xs font-medium text-slate-300 mb-1">
            {field.label}
          </label>
          <input
            type="number"
            value={val !== undefined && val !== null ? String(val) : String(field.default ?? '')}
            placeholder={field.placeholder}
            onChange={(e) =>
              setConfig((prev) => ({
                ...prev,
                [field.name]: e.target.value === '' ? '' : Number(e.target.value),
              }))
            }
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
          />
          {field.description && (
            <p className="text-[11px] text-slate-500 mt-1">{field.description}</p>
          )}
        </div>
      );
    }

    return (
      <div key={field.name}>
        <label className="block text-xs font-medium text-slate-300 mb-1">
          {field.label}
        </label>
        <input
          type="text"
          value={String(val ?? '')}
          placeholder={field.placeholder}
          onChange={(e) => setConfig((prev) => ({ ...prev, [field.name]: e.target.value }))}
          className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
        />
        {field.description && (
          <p className="text-[11px] text-slate-500 mt-1">{field.description}</p>
        )}
      </div>
    );
  };

  const connectionFields = (activeSpec?.config_schema || []).filter(
    (f) => f.group === 'connection'
  );
  const simulationFields = (activeSpec?.config_schema || []).filter(
    (f) => f.group === 'simulation'
  );

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-4xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between gap-4 shrink-0">
          <div>
            <h2 className="text-lg font-bold text-white">
              {isEditing ? `Edit Source — ${existing?.name}` : 'Configure Universal Log / Event Source'}
            </h2>
            <p className="text-xs text-slate-400">
              Define any connector specification (Webhook, REST API, SSE, Log File, Kafka, RabbitMQ, or Custom) with zero code changes.
            </p>
          </div>

          <div className="flex items-center gap-2">
            {!isEditing && (
              <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800">
                <button
                  type="button"
                  onClick={() => setEditorMode('form')}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition ${
                    editorMode === 'form'
                      ? 'bg-amber-500 text-slate-950 font-semibold'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Sliders className="w-3.5 h-3.5" />
                  Form View
                </button>
                <button
                  type="button"
                  onClick={() => setEditorMode('raw')}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition ${
                    editorMode === 'raw'
                      ? 'bg-amber-500 text-slate-950 font-semibold'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <Code2 className="w-3.5 h-3.5" />
                  Raw YAML / JSON
                </button>
              </div>
            )}

            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {editorMode === 'raw' && !isEditing ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold uppercase tracking-wider text-amber-400">
                  Config-as-Code Specification (YAML or JSON)
                </label>
                <span className="text-[11px] text-slate-400">
                  Paste any valid YAML or JSON source spec to create it immediately.
                </span>
              </div>
              <textarea
                rows={18}
                value={rawSpecText}
                onChange={(e) => setRawSpecText(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-xl p-4 text-xs font-mono text-emerald-300 focus:outline-none focus:border-amber-500"
              />
            </div>
          ) : (
            <>
              {/* 1. Source Type Selector */}
              <section className="space-y-2.5">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Source Connector Type
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
                  {types.map((t) => {
                    const selected = t.kind === kind;
                    return (
                      <button
                        key={t.kind}
                        type="button"
                        onClick={() => handleSelectKind(t.kind)}
                        className={`p-2.5 rounded-xl border text-left transition flex flex-col gap-1 ${
                          selected
                            ? 'bg-amber-500/15 border-amber-500 text-white shadow'
                            : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-600 hover:text-slate-200'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <KindIcon
                            icon={t.icon}
                            className={`w-4 h-4 ${selected ? 'text-amber-400' : 'text-slate-500'}`}
                          />
                          <span className="text-[9px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                            {t.mode}
                          </span>
                        </div>
                        <div className="text-xs font-semibold leading-tight mt-0.5">
                          {t.label}
                        </div>
                      </button>
                    );
                  })}
                </div>
                {activeSpec && (
                  <p className="text-xs text-slate-400">{activeSpec.description}</p>
                )}
              </section>

              {/* 2. Basic Metadata */}
              <section className="pt-2 border-t border-slate-800">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Source Name *
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. trade-gateway or payments-kafka"
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
                  />
                </div>
              </section>

              {/* 3. Dynamic Connection Spec */}
              {connectionFields.length > 0 && (
                <section className="space-y-3 pt-2 border-t border-slate-800">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Connection Specification ({activeSpec?.label})
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {connectionFields.map(renderConfigField)}
                  </div>
                </section>
              )}

              {/* 3. Parsing, Envelope Unwrapping & Field Aliases (Idea 5) */}
              <section className="space-y-3 pt-2 border-t border-slate-800">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Schema-Less Parsing, Envelope Unwrapping & Field Aliases
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Input Format Parser
                    </label>
                    <select
                      value={String(config.parser || 'auto')}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev,
                          parser: e.target.value,
                          regex_pattern:
                            e.target.value === 'regex' && !prev.regex_pattern
                              ? DEFAULT_LOG_REGEX
                              : prev.regex_pattern,
                        }))
                      }
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
                    >
                      <option value="auto">Auto-detect (JSON / NDJSON / Key-Value / Regex)</option>
                      <option value="json">Strict JSON (object or array)</option>
                      <option value="ndjson">NDJSON (JSON Lines)</option>
                      <option value="key_value">Key=Value Log Lines</option>
                      <option value="regex">Custom Regex (Named Capture Groups)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Envelope Unwrap Path (optional)
                    </label>
                    <input
                      type="text"
                      value={String(config.root_path || '')}
                      onChange={(e) =>
                        setConfig((prev) => ({ ...prev, root_path: e.target.value }))
                      }
                      placeholder="e.g. payload or data.event (leave blank to keep envelope)"
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-amber-500"
                    />
                  </div>

                  {config.parser === 'regex' && (
                    <div className="sm:col-span-2">
                      <label className="block text-xs font-medium text-slate-300 mb-1">
                        Regex Pattern with Named Groups <code className="text-amber-400">(?P&lt;field&gt;...)</code>
                      </label>
                      <input
                        type="text"
                        value={String(config.regex_pattern || DEFAULT_LOG_REGEX)}
                        onChange={(e) =>
                          setConfig((prev) => ({ ...prev, regex_pattern: e.target.value }))
                        }
                        className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-amber-200 focus:outline-none focus:border-amber-500"
                      />
                    </div>
                  )}
                </div>

                {/* Field Aliases Editor */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium text-slate-300">
                      Field Aliases (map arbitrary incoming fields to normalized names)
                    </span>
                    <button
                      type="button"
                      onClick={() => setAliases((prev) => [...prev, { from: '', to: '' }])}
                      className="px-2.5 py-1 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/30 text-xs font-semibold text-amber-300 flex items-center gap-1 transition"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add Alias
                    </button>
                  </div>
                  {aliases.map((row, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <input
                        type="text"
                        value={row.from}
                        placeholder="Incoming path (e.g. err.msg)"
                        onChange={(e) =>
                          setAliases((prev) =>
                            prev.map((r, i) => (i === idx ? { ...r, from: e.target.value } : r))
                          )
                        }
                        className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-white"
                      />
                      <span className="text-slate-500 text-xs">→</span>
                      <input
                        type="text"
                        value={row.to}
                        placeholder="Target field (e.g. error.message)"
                        onChange={(e) =>
                          setAliases((prev) =>
                            prev.map((r, i) => (i === idx ? { ...r, to: e.target.value } : r))
                          )
                        }
                        className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-white"
                      />
                      <button
                        type="button"
                        onClick={() => setAliases((prev) => prev.filter((_, i) => i !== idx))}
                        className="p-1.5 text-slate-500 hover:text-rose-400"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </section>

              {/* 6. Sample Event & Live Dry-Run Against Rules (Idea 3) */}
              <section className="space-y-3 pt-2 border-t border-slate-800">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Unseen Schema Playground & Live Rule Dry-Run
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {presets.slice(0, 4).map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => handleApplyPreset(p.id)}
                        className="text-[11px] px-2 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
                      >
                        {p.label.replace(' (Appendix A)', '')}
                      </button>
                    ))}
                  </div>
                </div>

                <textarea
                  rows={5}
                  value={sampleText}
                  onChange={(e) => setSampleText(e.target.value)}
                  placeholder='Paste any unseen JSON payload or raw log line here to auto-discover fields and dry-run against active rules...'
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl p-3 text-xs font-mono text-emerald-300 focus:outline-none focus:border-amber-500"
                />

                <div className="flex items-center justify-start gap-3">
                  <button
                    type="button"
                    disabled={dryRunLoading}
                    onClick={handleDryRun}
                    className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-600 text-xs font-semibold text-amber-300 flex items-center gap-1.5 transition"
                  >
                    <Play className="w-3.5 h-3.5" />
                    {dryRunLoading ? 'Running Dry-Run...' : 'Dry-Run Parse & Match Rules'}
                  </button>
                </div>

                {dryRunError && (
                  <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                    <span>{dryRunError}</span>
                  </div>
                )}

                {dryRunResult && (
                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-700 space-y-4">
                    {/* Detected Fields */}
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
                        Detected Schema Fields ({dryRunResult.detected_fields.length})
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {dryRunResult.detected_fields.map((f) => (
                          <span
                            key={f.path}
                            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-slate-900 border border-slate-700 text-[11px] font-mono text-slate-200"
                          >
                            <span className="text-amber-400">{f.path}</span>
                            <span className="text-slate-500">({f.type})</span>
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Matched Rules */}
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
                        Active Rules Matched ({dryRunResult.matched_rules.length}) — No Alert Persisted
                      </div>
                      {dryRunResult.matched_rules.length === 0 ? (
                        <div className="text-xs text-slate-500 italic">
                          No active rules matched this sample payload.
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {dryRunResult.matched_rules.map((m) => (
                            <div
                              key={m.rule_id}
                              className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 space-y-1"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <div className="flex items-center gap-2 text-xs font-semibold text-emerald-300">
                                  <CheckCircle2 className="w-4 h-4" />
                                  {m.rule_name}
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-900 text-slate-300 font-mono">
                                    {m.team}
                                  </span>
                                </div>
                                <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-slate-900 text-amber-300">
                                  {m.severity} • {m.channels.join(', ')}
                                </span>
                              </div>
                              <div className="text-xs text-white font-medium">
                                Preview: {m.rendered_title}
                              </div>
                              {m.rendered_body && (
                                <div className="text-[11px] text-slate-300">{m.rendered_body}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </section>

              {/* 5. Simulation Mode Settings (at the very bottom) */}
              {simulationFields.length > 0 && (
                <section className="space-y-3 pt-2 border-t border-slate-800">
                  <div className="text-xs font-semibold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5" />
                    Built-in Simulation Settings (Optional — Test Without External Infra)
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {simulationFields.map(renderConfigField)}
                  </div>
                </section>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-900/80 shrink-0 space-y-3">
          {saveError && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{saveError}</span>
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="rounded border-slate-600 bg-slate-950 text-amber-500 focus:ring-amber-500"
              />
              Enable source immediately on save
            </label>
            <div className="flex items-center gap-2 ml-auto">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-slate-300 hover:text-white hover:bg-slate-800 transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={handleSave}
            className="px-5 py-2 rounded-lg text-sm font-semibold bg-amber-500 hover:bg-amber-400 text-slate-950 disabled:opacity-50 transition"
          >
            {saving
              ? 'Saving...'
              : editorMode === 'raw' && !isEditing
              ? 'Import & Create Source'
              : isEditing
              ? 'Save Changes'
              : 'Create Source'}
          </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
