// Wspólne typy = kształt JSON z backendu (models.py). Zmiana tutaj = zmiana w models.py i odwrotnie.
// Typy reguł są w rules/ruleTypes.ts.
import type { Channel, Color, Severity } from '../rules/ruleTypes';

export type AlertStatus = 'open' | 'acknowledged' | 'resolved';

export interface RunbookStep {
  text: string;
  action: string | null;          // retry_workflow | restart_service | http_get | escalate | webhook | open_ticket
  params: Record<string, unknown>;
  approval: 'none' | 'required';
  done?: boolean;
  done_by?: string;               // kto oznaczył krok jako zrobiony
  done_at?: string;
  approved_by?: string;           // kto zatwierdził ryzykowny krok
  approved_at?: string;
  // Wykonywanie kroków (services/runbook_runner.py)
  condition?: string | null;      // "retry fails twice" – krok wykona się tylko, gdy warunek jest spełniony
  kind?: StepKind | null;         // ręcznie wybrany rodzaj; null = wykryty automatycznie
  custom?: boolean;               // własna akcja zespołu (Runbooks → Actions), np. "clear_cache"
  status?: StepStatus | null;
  result?: string | null;         // co się stało, np. "settlement responded 200 OK"
  run_no?: number;                // 2, 3… po kliknięciu "Retry"
  executed_by?: string;
  finished_at?: string;
}

export type StepKind = 'manual' | 'auto' | 'approve' | 'approve_manual';
export type StepStatus = 'waiting' | 'waiting_approval' | 'succeeded' | 'failed' | 'skipped';

export interface Alert {
  id: number;
  rule_id: string;
  team: string;
  dedup_key: string;
  title: string;
  body: string | null;
  severity: Severity;
  color: Color;
  status: AlertStatus;
  count: number;
  steps: RunbookStep[];
  history: { at: string; who: string; what: string }[];
  first_seen: string;
  last_seen: string;
}

export interface Person {
  id: number;
  name: string;
  team: string;
  email: string | null;
  phone: string | null;
  on_call: boolean;
  role: 'member' | 'lead';       // lead approves risky runbook steps for the team
  channel_prefs: Partial<Record<Severity, Channel[]>>;
  quiet_hours: Partial<Record<Channel, { from: string; to: string; else: Channel }>>;
}

export type SourceKind =
  | 'webhook'
  | 'polled_api'
  | 'sse'
  | 'logfile'
  | 'kafka'
  | 'rabbitmq'
  | 'custom';

export interface Source {
  id: number;
  key: string;                    // ingest URL: /api/ingest/{key}
  ingest_url?: string;
  name: string;
  team: string;
  kind: SourceKind;
  config: Record<string, unknown>;
  sample_event: unknown | null;
  detected_fields?: { path: string; type: string; example: unknown }[];
  enabled: boolean;
  status: 'active' | 'paused' | 'error' | 'simulating';
  last_error: string | null;
  last_event_at: string | null;
  events_count: number;
  worker_running?: boolean;
  created_at: string;
}

export interface Delivery {
  id: number;
  alert_id: number;
  person_id: number | null;
  channel: Channel;
  to: string | null;
  status: 'pending' | 'sending' | 'sent' | 'failed' | 'dead';
  attempts: number;
  max_attempts?: number;
  exhausted?: boolean;
  last_error: string | null;
  created_at: string;
  sent_at: string | null;
  subject?: string | null;
  body?: string | null;
  next_attempt_at?: string | null;
  recipient_name?: string | null;
  reply_code?: string | null;
}

// Udawana bramka SMS / telefon (widok "fałszywego telefonu")
export interface GatewayMessage {
  id: number;
  channel: 'sms' | 'phone';
  direction: 'out' | 'in';   // out = do człowieka, in = odpowiedź człowieka
  number: string;
  body: string;
  delivery_id: number | null;
  created_at: string;
}

export interface ChannelState {
  channel: Channel;
  down: boolean;
}

export interface Runbook {
  id: number;
  name: string;
  format: 'yaml' | 'json' | 'html' | 'markdown' | 'text' | 'link';
  raw: string;
  steps: RunbookStep[];
  matches?: Record<string, unknown> | null;
}
