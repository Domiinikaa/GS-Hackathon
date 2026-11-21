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

### 2. Rules, Alerts, Runbooks & Delivery Pipeline
- **Normalized Event Contract for Rules:** Every ingested record (regardless of transport or raw log format) is parsed, unwrapped (`root_path`), and aliased (`field_aliases`) before being stored in `Event.payload` as a structured JSON object. Rule evaluators (`services/rules_engine.py`) can query nested fields via dot-notation (e.g. `payload.notional`, `error.code`) and build recursive `and`/`or`/`not` condition trees, while rule editors can consume `detected_fields` from `GET /api/sources` or `GET /api/sources/{id}/fields` for field autocomplete.
- **Event Pipeline (`services/pipeline.py`):** Evaluates incoming events against enabled rules, deduplicates/groups alerts, resolves on-call recipients and channel preferences, and enqueues deliveries.
- **Security & Access Control:**
  - JWT authentication (`HS256`), single-use invite-code registration (`GS-XXXX-XXXX`), and dynamic company departments.
  - Clean database initialization with environment-based or CLI admin provisioning (`ADMIN_UNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` or `create_admin.py`).
  - Source management endpoints use a centralized `require_source_manager` dependency in `routers/sources.py` (currently open to authenticated/local testing; set `REQUIRE_ADMIN_FOR_SOURCES = True` to restrict source mutations to administrators).

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

Required/recommended environment variables for production:
- `DATABASE_URL` — PostgreSQL connection string (required for multi-replica deployments; defaults to local SQLite `app.db` if unset)
- `SECRET_KEY` — shared JWT signing key across all replicas
- `ADMIN_UNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` — automatic bootstrap for the first administrator account
- `PORT` — HTTP port (defaults to `8000`)

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

### Authentication & Administration (`/api/auth`, `/api/admin`)
| Method | Endpoint | Description | Access |
|---|---|---|---|
| `POST` | `/api/auth/register` | Register using a single-use invite code | Public |
| `POST` | `/api/auth/login` | Authenticate with username/email and password | Public |
| `GET` | `/api/auth/me` | Fetch authenticated user profile | Bearer JWT |
| `PUT` | `/api/auth/me` | Update phone number or department | Bearer JWT |
| `GET` | `/api/departments` | List active company departments | Public |
| `POST` | `/api/admin/invites` | Generate a single-use invite code | Admin Only |
| `GET` | `/api/admin/invites` | List generated invite codes | Admin Only |
| `GET` | `/api/admin/users` | List registered users | Admin Only |
| `PATCH` | `/api/admin/users/{id}/role` | Promote or demote administrator privileges | Admin Only |
| `POST` | `/api/admin/departments` | Create a company department | Admin Only |
| `PUT` | `/api/admin/departments/{id}` | Update a department | Admin Only |
| `DELETE` | `/api/admin/departments/{id}` | Delete a department | Admin Only |

### Alerting Pipeline (`/api`)
| Resource | Prefix | Description |
|---|---|---|
| Alerts | `/api/alerts` | Live alerts feed, acknowledge, and resolve actions |
| Rules | `/api/rules` | Runtime rule management (conditions, templates, routing, grouping) |
| People | `/api/people` | On-call responders, channel preferences, and quiet hours |
| Runbooks | `/api/runbooks` | Remediation steps (YAML, Markdown, text, or link) |
| Deliveries | `/api/deliveries` | Notification outbox and delivery retry status |
| Health | `/health` | Service uptime check |
