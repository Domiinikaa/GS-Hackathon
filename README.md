# GS Alerting & Orchestration Engine

**Flexible Alerting & Notification Service** built for the Goldman Sachs Software Engineering Hackathon.

The platform ingests heterogeneous events and logs from arbitrary sources, evaluates dynamic filtering rules at runtime, deduplicates and groups alerts, attaches actionable runbooks, and delivers notifications through each responder's preferred channels.

---

## System Architecture

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                         CLIENT SPA (React 18 + TS)                       │
│   Alerts • Rules • People • Universal Sources • Runbooks • Outbox • Admin│
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │ HTTP / JSON (Bearer JWT)
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       FASTAPI BACKEND ENGINE                             │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ Universal Ingestion & Connector Manager                            │  │
│  │ • Push: HTTP Webhook, Custom Spec (/api/ingest/{key})              │  │
│  │ • Pull / Stream: Polled REST API, SSE, Tailed Log File, Kafka, AMQP│  │
│  │ • Schema-less Parser (JSON, NDJSON, Key=Value, Regex)              │  │
│  │ • Envelope Unwrapping (root_path) & Field Aliases                  │  │
│  │ • Built-in Per-Source Event Simulator                              │  │
│  └─────────────────────────────────┬──────────────────────────────────┘  │
│                                    ▼                                     │
│     Pipeline: Event ─► Rules Engine ─► Alert Dedup ─► People ─► Outbox   │
│                                                                          │
│                        SQLAlchemy 2.0 ORM                                │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
                                     ▼
                     PostgreSQL (Production) / SQLite (Dev)
```

---

## Key Capabilities

### End-to-End Integrated Pipeline (`services/pipeline.py`)
All core subsystems — **Sources / Streams**, **Rules**, **Runbooks**, **Alerts**, **People**, and **Notification Channels / Outbox** — are fully connected in production via `process_event()`:
1. Any record arriving from HTTP push (`POST /api/ingest/{source_key}`), background stream/pull connectors (`polled_api`, `sse`, `logfile`, `kafka`, `rabbitmq`), or the simulator (`POST /api/sources/{id}/simulate`) is normalized and persisted as an `Event`.
2. `evaluate()` runs active rules against the event, attaches the rule's linked `Runbook` (or auto-matches a runbook via `Runbook.matches`), and renders `{{field}}` templates in alert titles, bodies, and runbook step `params`.
3. `upsert_alert()` creates or deduplicates the open `Alert` and publishes it to the live SSE stream (`/api/alerts/stream`).
4. When a new alert is created (`_is_new`), `recipients_for()` resolves team members, `on_call` rules, and `quiet_hours`, and `enqueue_deliveries()` queues formatted Email/SMS/Phone notifications in the Outbox for the background delivery worker.

### 1. Universal Log & Event Sources (`services/connectors/`, `routers/sources.py`)
Designed around a **declarative Connector Registry** (`CONNECTOR_REGISTRY`) so new source types can be added without modifying frontend forms. The UI dynamically renders configuration fields from `GET /api/sources/types`.

- **7 Supported Source Types (all with built-in Simulation Mode):**
  - **HTTP Webhook (`webhook`):** Push endpoint `POST /api/ingest/{key}` supporting JSON objects, JSON arrays, NDJSON, and plain-text logs, with optional `api_key`, `bearer`, or `hmac_sha256` verification.
  - **Polled REST API (`polled_api`):** Background `httpx` poller with configurable HTTP method, headers, `interval_s`, `records_path` extraction, and `cursor_field` deduplication.
  - **SSE Event Stream (`sse`):** Live `text/event-stream` subscriber with configurable rate limiting (`max_events_per_min`).
  - **Tailed Log File (`logfile`):** Continuous file tailer supporting log rotation; in Simulation Mode, appends realistic log lines directly to disk.
  - **Apache Kafka (`kafka`):** Consumes from a Kafka topic (via `aiokafka` when available) or runs an in-process broker simulation with `_kafka` metadata.
  - **RabbitMQ / AMQP (`rabbitmq`):** Consumes from an AMQP queue (via `aio-pika` when available) or runs an in-process simulation with `_amqp` metadata.
  - **Custom / Universal Spec (`custom`):** Arbitrary JSON/YAML integration specification with push ingest or simulation.
- **Schema-Less Parsing & Normalization:**
  - Supports `auto`, `json`, `ndjson`, `key_value`, and `regex` (named capture groups) modes.
  - **Envelope Unwrapping (`root_path`):** Extracts nested event bodies (e.g. `payload` or `envelope.body`) while retaining outer metadata under `_envelope`.
  - **Field Aliases (`field_aliases`):** Maps arbitrary incoming dot-paths to normalized field names.
  - **Automatic Field Discovery:** Recursively extracts dot-notation paths and data types from sample or live events.
- **Config-as-Code (YAML / JSON):**
  - Create sources via `POST /api/sources/import` or the UI's **Form View ↔ Raw YAML / JSON** toggle.
  - Export any source specification with masked secrets via `GET /api/sources/{id}/export`.
- **Unseen Schema Playground & Rule Dry-Run:**
  - Paste any unseen JSON payload or raw log line into `POST /api/sources/dry-run` (or the UI playground) to inspect parsed output, discovered fields, and matching active rules **without persisting events or alerts**.
  - Supports **arbitrarily nested / recursive `and`, `or`, and `not` condition trees** as well as leaf `{field, op, value}` conditions.
- **Built-in Simulator & Connection Tester:**
  - Simulate 1–50 realistic events for any source (`POST /api/sources/{id}/simulate`) using Appendix A presets or custom payloads, and probe live connectivity via `POST /api/sources/{id}/test-connection`.
- **Live Event Inspector:**
  - Real-time event viewer (`GET /api/events`) with source filtering, payload search, and auto-refresh.

### 2. Rules Engine & Multi-Format Runbooks (`services/rules_engine.py`, `services/runbook_parser.py`)
- **Dynamic Rule Evaluation:**
  - Supports arbitrarily nested `and`, `or`, and `not` condition trees with leaf operators (`eq`, `neq`, `gt`, `lt`, `gte`, `lte`, `contains`, `wildcard`, `regex`, `in`) queried via dot-notation (`payload.notional`, `error.code`).
  - Dynamic `{{field}}` template interpolation in alert titles, bodies, and runbook step parameters.
  - Per-rule `severity` (`info`, `warning`, `critical`), `color`, `channels`, and time-window grouping (`group_by`, `group_window_s`).
  - Interactive dry-run endpoint (`POST /api/engine/test`) and live field hints (`GET /api/rules/fields`).
- **Multi-Format Runbook Parser (`POST /api/runbooks/parse-preview`, `routers/runbooks.py`):**
  - Parses **YAML**, **JSON**, **HTML**, **Markdown**, **plain text**, and **URL link** runbooks into structured steps with `text`, `action`, `params`, and `approval` (`none` | `required`).
  - Automatic `matches` criteria on runbooks attach matching runbooks to alerts at evaluation time even when a rule has no explicit `runbook_id`.
  - Detects approval-required steps from explicit `approval: required` or natural-language phrases (e.g. `needs approval`).

### 3. Alert Deduplication, Live Stream & Step Approvals (`services/alert_service.py`, `routers/alerts.py`, `services/live.py`)
- **Anti-Flood Open-Alert Deduplication:**
  - Enforced at the database level via partial unique index `uq_alerts_open_dedup` on `alerts(dedup_key) WHERE status != 'resolved'` and atomic `ON CONFLICT ... DO UPDATE ... RETURNING` in `upsert_alert()`.
  - Repeated events increment `Alert.count` and refresh `last_seen`, while **notifications are dispatched only once when a new alert is created** (until the alert is resolved and a fresh occurrence opens a new alert).
- **Real-Time Live Feed (`GET /api/alerts/stream`):**
  - Server-Sent Events (SSE) stream using in-memory pub/sub locally or PostgreSQL `LISTEN/NOTIFY` across multiple backend replicas.
- **Incident Lifecycle & RBAC Step Approvals:**
  - `open -> acknowledged -> resolved` state machine with full `history` audit trail.
  - Risky runbook steps (`approval: "required"`) cannot be marked `done` until approved via `POST /api/alerts/{id}/steps/{step_index}/approve`, restricted to a `lead` of the alert's team or an administrator (`is_admin`).

### 4. Unified Teams, People & Escalation Routing (`services/people_service.py`, `routers/people.py`, `routers/admin.py`)
- **Single Unified `Team` Directory:**
  - Shared across Auth (`User`), Admin & Teams (`/api/teams`, `/api/admin/teams`), People, Rules, Sources, and Alerts (with a `My team` quick filter in the Alerts UI).
  - Registering or updating a user profile (`POST /api/auth/register`, `PUT /api/auth/me`) validates the team and automatically creates/syncs the matching `Person` profile.
  - Renaming a team cascades across `users`, `people`, `rules`, `sources`, and `alerts`; deleting a team with active members or rules is guarded (`409 Conflict`).
- **Smart Recipient Planning (`recipients_for`):**
  - Resolves per-severity `channel_prefs`, restricts `phone` calls to `on_call=True` responders, enforces `quiet_hours` fallbacks (including `"ui"`), falls back to `email` when `phone` is missing, and distinguishes `member` vs `lead` roles.

### 5. Notification Channels, Outbox & Two-Way Replies (`services/delivery.py`, `services/channels/`, `services/replies.py`)
- **Pluggable Channel Registry (`services/channels/registry.py`):**
  - **Email (`SmtpEmail`, `EMAIL_PROVIDER=smtp`):** Sends multipart plain-text + styled HTML emails with severity accents, runbook steps, and `#alerts/{id}` deep links (works out of the box with Mailpit on `localhost:1025` or any SMTP server via `SMTP_*` env vars).
  - **SMS & Voice Phone (`FakeSms`, `FakePhone`, `SMS_PROVIDER=fake`, `PHONE_PROVIDER=fake`):** Concise ≤160-char SMS payloads with 4-digit `reply_code` and voice-call scripts logged to `gateway_messages` and displayed in the **Fake phone** UI inside Outbox.
- **Reliable Outbox Worker:**
  - Background worker (`start_worker` / `process_due`) claims pending/failed deliveries via atomic `UPDATE ... WHERE status IN (...)` leases (safe across multiple replicas), retries with exponential backoff (`2^attempts` seconds up to `MAX_ATTEMPTS = 5`), and marks exhausted rows as `dead`.
  - Simulated channel outage toggles (`PUT /api/channels/{channel}/outage` for `sms` and `phone`) demonstrate retry recovery in the Outbox UI.
- **Two-Way SMS & Phone Responses:**
  - Responders can reply directly from the **Fake phone** widget or via webhooks:
    - `POST /api/channels/sms/inbound`: `ACK <code>` (acknowledge), `YES <code>` / `APPROVE <code>` (approve next pending risky step), `RESOLVE <code>` (resolve alert) — verified against both recipient phone number and `reply_code`.
    - `POST /api/channels/phone/inbound`: press `1` to acknowledge the latest alert call.

### 6. Security, Access Control & Seed Data (`seed.py`, `routers/auth.py`)
- JWT authentication (`HS256`), single-use invite-code registration (`GS-XXXX-XXXX`), and environment/CLI admin provisioning (`ADMIN_UNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` or `create_admin.py`).
- Automatic startup seeding (under `startup_lock()`) for empty tables: 5 unified teams (`Settlements`, `Pricing`, `Rates`, `Payments`, `Management`), 5 sources (`demo`, `trade-gateway`, `payments-webhook`, `settlement-kafka`, `pricing-engine-logs`), 4 rules, 3 members + 4 team leads, and 3 Appendix B runbooks (YAML, Markdown, text).
- Source management endpoints use a centralized `require_source_manager` dependency in `routers/sources.py` (open for local/hackathon testing by default; set `REQUIRE_ADMIN_FOR_SOURCES = True` to restrict source mutations to administrators).

---

## Local Development Quickstart

### Prerequisites
- Python 3.11+
- Node.js 18+ & npm

### One-Command Startup
```bash
./start.sh
```
Or build the frontend and run in unified production mode on a single port:
```bash
./start.sh --prod
```

### Manual Multi-Terminal Startup

#### Backend (FastAPI)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: create an initial administrator
python create_admin.py --uname admin --email admin@goldmansachs.com --password AdminSecret123!

uvicorn main:app --reload
```
- API Base: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

#### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```
- Dev Server: `http://localhost:5173` (proxies `/api` requests to `http://localhost:8000`).

---

## Cloud Deployment (Docker / Railway)

The included multi-stage `Dockerfile` compiles the React + TypeScript bundle with Node 20 and serves both the FastAPI backend and static SPA from Python 3.11 on a single port.

Required/recommended environment variables for production (see `.env.example`):
- `DATABASE_URL` — PostgreSQL connection string (required for multi-replica deployments; defaults to local SQLite `app.db` if unset)
- `SECRET_KEY` — shared JWT signing key across all replicas
- `ADMIN_UNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` — automatic bootstrap for the first administrator account
- `PORT` — HTTP port (defaults to `8000`)
- `APP_URL` — base frontend URL used for `#alerts/{id}` deep links in emails and SMS (defaults to `http://localhost:5173`)
- `EMAIL_PROVIDER`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_STARTTLS`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` — SMTP delivery configuration (defaults to Mailpit on `localhost:1025`)
- `SMS_PROVIDER`, `PHONE_PROVIDER` — channel provider selection (default `fake`)

### Production Horizontal Scaling (N Replicas / Kubernetes)
All application instances are stateless and coordinate exclusively through the shared PostgreSQL database:
1. **Shared Database:** Point every replica to the same PostgreSQL instance via `DATABASE_URL` (use **PgBouncer** in transaction/session pooling mode when running many pods).
2. **Automatic Worker Coordination:**
   - **Singleton Pull/Stream Workers (`polled_api`, `sse`, `logfile`, `simulate=True`):** Coordinated automatically via PostgreSQL session advisory locks (`pg_try_advisory_lock`) and a 5-second DB reconciler loop so only one replica polls each source, with automatic failover if a pod terminates.
   - **Broker Streams (`kafka`, `rabbitmq`):** Run across all replicas simultaneously using Kafka consumer groups (`group_id`) and RabbitMQ competing consumers.
   - **Atomic Counters & Cursor Persistence:** `Source.events_count` uses atomic SQL increments (`coalesce(events_count, 0) + N`), and `polled_api` deduplication cursors are persisted in PostgreSQL (`_seen_cursors`).
3. **Kubernetes / HPA Readiness:**
   - Configure `livenessProbe` and `readinessProbe` on `GET /health`.
   - Scale the `Deployment` with a `HorizontalPodAutoscaler` (CPU/RPS) behind a standard Kubernetes `Service` / Ingress.
   - For high-volume container logs in Kubernetes, run **Fluent Bit** or **Vector** as a DaemonSet forwarding logs to `POST /api/ingest/{key}` (or Kafka) rather than tailing local pod files.
4. **High-Throughput Next Steps (10k+ msg/s):** Decouple `POST /api/ingest/{key}` into a `202 Accepted` queue producer (Kafka/RabbitMQ) with dedicated worker pods scaled via KEDA, and apply time-based partitioning to the `events` table.

---

## REST API Reference

### Sources & Ingestion (`/api`)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/sources/types` | List registered connector schemas, simulator presets, and capabilities |
| `GET` | `/api/sources` | List configured sources with masked secrets, status, and event counts |
| `POST` | `/api/sources` | Create a new source and start its background worker if enabled |
| `PUT` | `/api/sources/{id}` | Update source specification and hot-reload its worker |
| `PATCH` | `/api/sources/{id}/toggle` | Enable or pause a source at runtime |
| `DELETE` | `/api/sources/{id}` | Delete a source and stop its worker (preserves event history) |
| `POST` | `/api/sources/import` | Create a source from a raw YAML or JSON specification |
| `GET` | `/api/sources/{id}/export` | Export a source specification as YAML or JSON (secrets masked) |
| `POST` | `/api/sources/dry-run` | Parse a sample payload, discover fields, and preview matching rules |
| `POST` | `/api/sources/{id}/simulate` | Emit 1–50 synthetic events for any source kind |
| `POST` | `/api/sources/{id}/test-connection` | Probe live connectivity for the configured source |
| `GET` | `/api/sources/{id}/fields` | Return discovered dot-notation fields from the source's sample event |
| `POST` | `/api/ingest/{source_key}` | Universal push endpoint (JSON object/array, NDJSON, or raw log text) |
| `GET` | `/api/events` | List recent ingested events (supports `limit` and `source_id` filters) |

### Authentication, Teams & Administration (`/api/auth`, `/api/teams`, `/api/admin`)
| Method | Endpoint | Description | Access |
|---|---|---|---|
| `POST` | `/api/auth/register` | Register using a single-use invite code (auto-creates `Person`) | Public |
| `POST` | `/api/auth/login` | Authenticate with username/email and password | Public |
| `GET` | `/api/auth/me` | Fetch authenticated user profile | Bearer JWT |
| `PUT` | `/api/auth/me` | Update phone number or team (syncs linked `Person`) | Bearer JWT |
| `GET` | `/api/teams` | List unified teams with member/rule/source counts | Public |
| `POST` | `/api/admin/invites` | Generate a single-use invite code | Admin Only |
| `GET` | `/api/admin/invites` | List generated invite codes | Admin Only |
| `GET` | `/api/admin/users` | List registered users | Admin Only |
| `PATCH` | `/api/admin/users/{id}/role` | Promote or demote administrator privileges | Admin Only |
| `POST` | `/api/admin/teams` | Create a team | Admin Only |
| `PUT` | `/api/admin/teams/{id}` | Rename/update a team (cascades across all entities) | Admin Only |
| `DELETE` | `/api/admin/teams/{id}` | Delete an empty team (`409` if members or rules exist) | Admin Only |

### Alerting Pipeline, Channels & Outbox (`/api`)
| Resource | Prefix / Endpoints | Description |
|---|---|---|
| Engine | `POST /api/engine/test` | Dry-run active or draft rules against a sample event |
| Alerts | `/api/alerts`, `GET /api/alerts/stream`, `POST /api/alerts/{id}/ack\|resolve`, `POST /api/alerts/{id}/steps/{idx}/approve\|done` | Live SSE alerts feed, dedup, acknowledge/resolve, and RBAC runbook step approvals |
| Rules | `/api/rules`, `GET /api/rules/fields` | Runtime rule management (conditions, templates, routing, grouping) |
| People | `/api/people`, `POST /api/people/preview` | On-call responders, `member`/`lead` roles, channel preferences, and quiet hours |
| Runbooks | `/api/runbooks`, `POST /api/runbooks/parse-preview` | Multi-format remediation steps (YAML, JSON, HTML, Markdown, text, link) |
| Outbox | `GET /api/deliveries`, `POST /api/deliveries/test` | Notification outbox, retry attempts, and test delivery trigger |
| Channels | `GET /api/channels`, `PUT /api/channels/{ch}/outage`, `GET /api/channels/phones\|messages`, `POST /api/channels/sms\|phone/inbound` | Channel status, outage simulator, Fake phone threads, and two-way SMS/phone replies |
| Health | `/health` | Service uptime check |

---

## Automated Tests

All backend tests run against isolated temporary SQLite databases without modifying `app.db`:
- `tests/test_engine.py` — Rules engine operators, grouping, templates, and multi-format runbook parsing
- `tests/test_api.py` — Runbook CRUD, engine preview API, and `/api/ingest` integration
- `tests/test_integration_pipeline.py` — End-to-end Sources → Rules → Runbooks → Alerts → People → Outbox, anti-flood dedup, step approval RBAC, and unified Teams
- `tests/test_channels_delivery.py` — SMTP email delivery, backoff & dead-letter retries, fake gateway outage recovery, two-way SMS/phone replies, and background worker lifecycle
- `tests/test_people_service.py`, `tests/test_rules_people_api.py`, `tests/test_people_roles.py` — Recipient planning, quiet hours, API validation, and team lead seeding/migrations
