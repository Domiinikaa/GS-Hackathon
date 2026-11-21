import type { Source, SourceKind } from '../shared/types';

export interface FieldSpec {
  name: string;
  label: string;
  type: 'string' | 'number' | 'boolean' | 'select' | 'secret' | 'json' | 'text';
  required: boolean;
  default: unknown;
  placeholder: string;
  description: string;
  options: string[];
  group: 'connection' | 'simulation' | 'parsing';
}

export interface ConnectorTypeSpec {
  kind: SourceKind;
  label: string;
  mode: 'push' | 'pull' | 'stream';
  description: string;
  icon: string;
  supports_simulation: boolean;
  config_schema: FieldSpec[];
}

export interface SimulatorPreset {
  id: string;
  label: string;
  description: string;
  format: 'json' | 'text';
  sample: unknown;
}

export interface SourceTypesResponse {
  types: ConnectorTypeSpec[];
  presets: SimulatorPreset[];
  yaml_supported: boolean;
  require_admin: boolean;
}

export interface ExtractedField {
  path: string;
  type: string;
  example: unknown;
}

export interface ConditionCheck {
  field: string;
  op: string;
  expected: unknown;
  actual: unknown;
  passed: boolean;
}

export interface MatchedRulePreview {
  rule_id: string;
  rule_name: string;
  team: string;
  severity: 'info' | 'warning' | 'critical';
  color: string;
  channels: string[];
  rendered_title: string;
  rendered_body: string;
  conditions: ConditionCheck[];
}

export interface DryRunResult {
  parsed_count: number;
  parsed_records: Record<string, unknown>[];
  detected_fields: ExtractedField[];
  matched_rules: MatchedRulePreview[];
}

export interface SimulateResult {
  source_id: number;
  kind: string;
  simulated_count: number;
  alerts: number[];
  last_parsed: Record<string, unknown> | null;
}

export interface TestConnectionResult {
  ok: boolean;
  mode: string;
  message: string;
}

export interface ExportSpecResult {
  format: 'yaml' | 'json';
  filename: string;
  content: string;
}

export interface EventRecord {
  id: number;
  source_id: number | null;
  source: {
    name: string;
    key: string;
    kind: string;
    team: string;
  } | null;
  payload: Record<string, unknown>;
  received_at: string | null;
}

export type SourceItem = Source;
