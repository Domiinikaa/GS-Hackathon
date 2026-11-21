# GS Alerting Engine

An alerting and incident-handling platform for teams in companies.

When something goes wrong in a company's systems (a payment fails, a trade is rejected, a service stops responding),
the right team has to find out quickly and know what to do. This platform takes in events and logs from any source,
checks them against rules that each team defines for itself, turns important events into alerts without flooding
people with duplicates, guides the team through a runbook (automatic actions, approvals, manual steps) and notifies
the right team members through their preferred channels: e-mail, SMS or a phone call.

Each team has its own members, leads, rules, sources and alerts, so many teams can work in one shared system.

**Live application:** [https://gs-hackathon-production.up.railway.app](https://gs-hackathon-production.up.railway.app/)

---

## Table of contents

1. [What it does](#what-it-does)
2. [How it works](#how-it-works)
3. [Features](#features)
4. [Tech stack](#tech-stack)
5. [How we used AI tools](#how-we-used-ai-tools)
6. [Getting started](#getting-started)
7. [Creating your account](#creating-your-account)
8. [How to use it](#how-to-use-it)
9. [Demo walkthrough](#demo-walkthrough)
10. [Configuration](#configuration)
11. [Scaling and deployment](#scaling-and-deployment)
12. [Project structure](#project-structure)
13. [API overview](#api-overview)
14. [Tests](#tests)

---

## What it does

Systems such as a trade gateway, a payments webhook or a pricing engine constantly produce events and logs.
Most of them are harmless, but some mean that something is broken and a person has to act. This service:

- **collects** events from many kinds of sources (HTTP webhooks, polled APIs, event streams, log files, Kafka, RabbitMQ),
- **understands** them without a fixed schema (JSON, NDJSON, `key=value`, regex for raw log lines),
- **decides** which events matter, using rules that teams create and edit in the UI,
- **creates alerts** with a severity, a colour and a readable title, and groups repeated events into one alert,
- **tells people what to do** by attaching a runbook, running safe steps automatically and asking for approval before risky ones,
- **notifies** the right team members through the right channel, respecting on-call status and quiet hours,
- **keeps a history** of who did what and when.

---

## How it works

### The path of one event

Every event, whatever source it came from, goes through the same pipeline (`services/pipeline.py`):

```text
 Source (webhook / API / stream / log / Kafka / RabbitMQ / simulator)
   │
   ▼
 1. Ingest & parse        services/connectors/        raw data -> normalised Event (saved in DB)
   │
   ▼
 2. Rules engine          services/rules_engine.py    which rules match? fill {{field}} templates
   │
   ▼
 3. Alert + dedup         services/alert_service.py   new alert, or count += 1 on the open one
   │
   ├──► Live feed         services/live.py            pushed to every open browser (SSE)
   │
   ▼
 4. Runbook runner        services/runbook_runner.py  run automatic steps, stop at steps that need a person
   │
   ▼
 5. Recipients            services/people_service.py  who should know, and through which channel
   │
   ▼
 6. Outbox & delivery     services/delivery.py        e-mail / SMS / phone, retried until it succeeds
```

1. **Ingest and parse.** An event arrives, for example through `POST /api/ingest/{source_key}`.
   The parser unwraps it (for example takes the body out of an `envelope`), renames fields using aliases
   and saves it as an `Event`.
2. **Rules engine.** Every active rule is checked against the event. A rule is a tree of conditions
   (`and`, `or`, `not`) with operators such as `eq`, `gt`, `contains`, `regex` or `in`, using dot paths such as
   `payload.notional`. When a rule matches, the alert title and body are filled in from the event,
   e.g. `Trade {{payload.tradeId}} rejected`.
3. **Alert and deduplication.** Each match has a `dedup_key`. If an open alert with the same key already exists,
   its counter goes up (`×500`) instead of creating 500 new alerts. This is enforced by the database itself,
   so it also works when several server copies receive events at the same time.
4. **Runbook runner.** The alert gets the rule's runbook (or a runbook whose `matches` criteria fit the event).
   Steps are run one by one: automatic steps are run straight away, and the runner stops at the first step
   that needs a person (an approval or a manual action).
5. **Recipients.** The service finds the people in the alert's team and picks a channel for each one,
   based on severity, on-call status, quiet hours and the person's preferences.
6. **Outbox.** Every notification is saved as a row in the outbox. A background worker sends it and,
   if the channel is down, retries with growing delays (2, 4, 8, 16 s) until it succeeds or gives up after 5 attempts.

People are notified **only when a new alert is created**. Repeated events only raise the counter,
so nobody gets flooded with messages.

---

## Features

### Sources: collecting events
- **7 source types:** HTTP webhook, polled REST API, SSE event stream, tailed log file, Apache Kafka, RabbitMQ (AMQP) and a custom spec.
- **Schema-less parsing:** `auto`, `json`, `ndjson`, `key_value` and `regex` (named groups) modes, envelope unwrapping (`root_path`) and field aliases.
- **Automatic field discovery:** the fields found in events are suggested when writing rules.
- **Built-in simulator:** every source can generate realistic test events, so the whole system can be shown without real systems.
- **Dry run:** paste any payload and see how it is parsed and which rules would match, without saving anything.
- **Config as code:** sources can be imported and exported as YAML or JSON (secrets are masked).
- **Webhook security:** optional `api_key`, `bearer` or `hmac_sha256` verification.

### Rules: deciding what matters
- Nested `and` / `or` / `not` conditions built in a visual editor.
- Operators: `eq`, `neq`, `gt`, `lt`, `gte`, `lte`, `contains`, `wildcard`, `regex`, `in`.
- Per-rule severity (`info`, `warning`, `critical`), colour, team, channels and linked runbook.
- `{{field}}` templates in titles and bodies.
- Grouping by fields within a time window (`group_by`, `group_window_s`).
- Rules can be tested against a sample event before they are saved.

### Alerts: handling incidents
- Deduplication with a counter and a "last seen" time.
- Live updates in the browser without refreshing (Server-Sent Events).
- Lifecycle `open → acknowledged → resolved`, with a full history of who did what and when.
- Direct links (`#alerts/<id>`) that open the alert, used in e-mails and SMS.
- Filters by status, severity and team ("My team").

### Runbooks: what to do next
- Runbooks can be written as **YAML, JSON, Markdown, HTML, plain text or a link**; the parser turns them into steps.
- Four kinds of steps:
  | Kind | Meaning |
  |---|---|
  | `auto` | the service runs the step by itself |
  | `approve` | the service runs the step after someone approves it |
  | `manual` | a person does it and clicks **Mark done** |
  | `approve_manual` | needs approval first, then a person does it |
- Built-in actions: HTTP check, retry workflow, restart service, webhook, open ticket, escalate, wait. Teams can also define their own actions.
- Conditional steps (e.g. "if the retry fails twice"): a step runs only when its condition is met, otherwise it is marked *skipped*.
- Risky steps can only be approved by a **lead** of the alert's team or an administrator, in the UI or by replying `YES <code>` to the SMS.
- Actions run on a safe simulator by default; real HTTP calls need `RUNBOOK_ALLOW_REAL_HTTP=1`.

### People and teams: who gets notified
- One shared list of teams used by users, people, rules, sources and alerts.
- Roles `member` and `lead`, on-call flag, phone number and e-mail.
- Channel preferences per severity, and quiet hours with a fallback channel.
- Phone calls only go to on-call people; if there is no phone number, e-mail is used instead.

### Notifications: delivery that does not lose alerts
- **E-mail** over real SMTP, with an HTML template showing the severity colour, the runbook steps and an "Open alert" button.
- **SMS and phone calls** through a fake gateway, shown on a **Fake phone** in the Outbox tab.
- **Two-way replies:** `ACK <code>` acknowledges, `YES <code>` / `APPROVE <code>` approves the next risky step, `RESOLVE <code>` resolves the alert; on a phone call, pressing `1` acknowledges.
- **Outbox with retries:** exponential backoff, at most 5 attempts, then the delivery is marked `dead`.
- New channels (e.g. Twilio, SendGrid) are added as one class in `services/channels/` and one line in `registry.py`.

### Security and access
We took care of security at every point where the application handles passwords, secrets or incoming data:

- **Password hashing:** passwords are never stored in plain text. They are hashed with **bcrypt**
  (12 rounds, a random salt for every password). If bcrypt is not available, the code falls back to
  **PBKDF2-HMAC-SHA256** with 100,000 iterations. Logging in compares the hash, never the password itself
  (`services/security.py`).
- **Signed login tokens:** after logging in, the user gets a **JWT** token signed with `SECRET_KEY` (HS256).
  The token expires after 24 hours, and every API request checks it (`routers/deps.py`).
- **Invite-only registration:** a new account needs a single-use invite code (`GS-XXXX-XXXX`), generated with
  Python's cryptographically secure `secrets` module. A used code cannot be used again (`routers/admin.py`, `routers/auth.py`).
- **Roles and permissions:** members, leads and administrators see and can do different things. For example, only
  a lead of the alert's team or an administrator can approve a risky runbook step, and the **Lead & Teams** panel is admin-only.
  These rules are checked in the backend, not only hidden in the UI.
- **Verified incoming data:** a webhook source can require an API key, a bearer token or an **HMAC-SHA256 signature**
  of the request body, so events from unknown senders are rejected. Secrets are compared in constant time
  (`hmac.compare_digest`) to prevent timing attacks (`routers/sources.py`).
- **Masked secrets:** passwords and tokens saved in source settings are shown as `********` in the UI, the API and
  exported YAML/JSON files, and are not overwritten when a source is edited (`services/connectors/registry.py`).
- **Data fingerprints:** records from polled APIs are identified by a **SHA-256** hash, so the same record is not
  processed twice (`services/connectors/ingest_manager.py`).
- **Safe runbook actions:** runbook actions run on a simulator by default; real HTTP calls must be enabled explicitly
  (`RUNBOOK_ALLOW_REAL_HTTP=1`).
- **Configuration outside the code:** keys and passwords (`SECRET_KEY`, `SMTP_PASSWORD`, `DATABASE_URL`) are read from
  environment variables, not stored in the repository.

---

## Tech stack

### Backend
| Tool | Used for |
|---|---|
| **Python 3.11** | main language of the backend |
| **FastAPI** | REST API, Server-Sent Events, automatic API docs (Swagger) |
| **Uvicorn** | ASGI server that runs the app |
| **SQLAlchemy 2.0** | ORM and database access |
| **PostgreSQL** | production database; `LISTEN/NOTIFY` for live updates across servers, advisory locks for workers |
| **SQLite** | local development database (no installation needed) |
| **Pydantic** | validation of requests and responses |
| **httpx** | polling external APIs, SSE sources, HTTP runbook actions |
| **aiokafka** | Kafka consumer |
| **aio-pika** | RabbitMQ (AMQP) consumer |
| **PyYAML** | YAML runbooks and source specs |
| **PyJWT, bcrypt** | authentication and password hashing |
| **smtplib** (standard library) | sending e-mails |
| **pytest** | automated tests |

### Frontend
| Tool | Used for |
|---|---|
| **React 18** | user interface |
| **TypeScript** | typed frontend code |
| **Vite** | dev server and production build |
| **Tailwind CSS** | styling |
| **lucide-react** | icons |
| **EventSource (SSE)** | receiving live alert updates in the browser |

### Infrastructure and tools
| Tool | Used for |
|---|---|
| **Docker** | multi-stage image: builds the frontend with Node 20, serves everything from Python 3.11 on one port |
| **Railway / Render** | cloud hosting |
| **Mailpit** | local test inbox for e-mails (`localhost:8025`) |
| **Git / GitHub** | version control and teamwork |

---

## How we used AI tools

### What we used them for
- **Debugging:** finding the cause of environment and library problems and of failing tests.
- **Code review:** before merging, an AI assistant reviewed our changes and pointed out possible bugs,
  edge cases and unclear code. Every suggestion was checked by a team member before it was accepted.
- **Synthetic test data:** generating mock datasets for testing and the demo (`seed.py`, the source simulators).

Product decisions, connecting the features together and the final verification were done by the team.

### Safe use of AI
- **No sensitive data in prompts:** we did not share real user data (PII), passwords, keys or company data with
  AI tools. We worked only with synthetic examples.
- **No secrets in the repository:** the project does not need any external API keys. Real settings
  (`SECRET_KEY`, `DATABASE_URL`, SMTP passwords) are kept in environment variables: locally in `.env`, which is
  excluded from git, and in production in the Railway variables. The database files (`*.db`) are excluded as well.
- **Testing by hand:** we did not trust generated code blindly. We tested the features and user flows end to end,
  found bugs, broken edge cases and unexpected behaviour, and fixed them step by step.

The data that the application itself stores (accounts, e-mail addresses, phone numbers) stays in our own database
and is protected as described in [Security and access](#security-and-access); passwords are only stored as hashes.

---

## Getting started

### Requirements
- Python 3.11+
- Node.js 18+ and npm
- (optional) [Mailpit](https://mailpit.axllent.org/) to see the e-mails locally

There are three ways to run the application:

| Mode | Command | Where it runs | When to use it |
|---|---|---|---|
| **Local development** | `./start.sh` | backend `:8000` + frontend `:5173` | writing code, changes are reloaded automatically |
| **Local production** | `./start.sh --prod` or Docker | everything on `:8000` | checking the final build before deploying |
| **Cloud (Railway)** | automatic deploy from GitHub | public `*.up.railway.app` address | the shared, always-on version |

### 1. Local development

**One command**
```bash
./start.sh
```
The script:
1. creates `.env` from `.env.example` if it does not exist,
2. creates the Python virtual environment `.venv` and installs `requirements.txt`,
3. installs the frontend packages (`npm install`) when needed,
4. starts the backend (FastAPI on `http://localhost:8000`) and the frontend (Vite on `http://localhost:5173`) together.

Changes in the code are picked up automatically. `Ctrl+C` stops both servers.
On Windows, run the script from **Git Bash**.

**Manual start (two terminals)**

*Backend*
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python create_admin.py --uname admin --email admin@example.com --password <your-password>
python seed.py                     # optional: sample teams, sources, rules and runbooks
# python seed.py --with-people     # also sample team members and leads

uvicorn main:app --reload
```

*Frontend*
```bash
cd frontend
npm install
npm run dev
```
In development the frontend forwards all `/api` requests to the backend on `:8000`.

| Address | What is there |
|---|---|
| `http://localhost:5173` | the application (dev mode) |
| `http://localhost:8000/docs` | interactive API docs (Swagger) |

The database starts empty. Sample data is loaded only when you run `python seed.py`.
Locally the data is stored in the SQLite file `app.db`; nothing has to be installed.

### 2. Local production mode

This runs the application the same way as in the cloud: the frontend is built once and served by the backend,
so everything is available on **one address**, `http://localhost:8000`.

**With the script**
```bash
./start.sh --prod
```
It builds the frontend (`npm run build` → `frontend/dist`) and starts the backend without auto-reload.

**With Docker**
```bash
docker build -t gs-alerting .
docker run -p 8000:8000 -e SECRET_KEY=<your-secret> gs-alerting
```
The `Dockerfile` has two stages: Node 20 builds the frontend, then Python 3.11 installs the backend
and serves both on the port from `$PORT` (default `8000`). Add `-e DATABASE_URL=postgresql://...` to use PostgreSQL.

### 3. Cloud deployment on Railway

Railway builds the application from the `Dockerfile` in this repository; no extra configuration file is needed.

**First setup (once)**
1. In Railway create a **New Project → Deploy from GitHub repo** and choose this repository.
   Railway finds the `Dockerfile` and builds the image.
2. In the same project add a **PostgreSQL** database (**+ New → Database → PostgreSQL**).
3. Open the application service → **Variables** and set:
   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (reference to the Railway database) |
   | `SECRET_KEY` | a long random string, the same for every copy of the server |
   | `APP_URL` | the public address of the app (used in links in e-mails and SMS) |
   | `SMTP_*`, `MAIL_FROM` | a real mail server, if e-mails should reach real inboxes |

   `PORT` is set by Railway automatically. A `postgres://` address from Railway is converted to the right format
   by `database.py`, so it can be pasted as it is.
4. **Settings → Networking → Generate Domain** gives the app a public address such as `https://<name>.up.railway.app`.
5. (recommended) **Settings → Healthcheck path:** `/health`.

**Opening the application**

Our deployed version is available at:

| Address | What is there |
|---|---|
| [https://gs-hackathon-production.up.railway.app](https://gs-hackathon-production.up.railway.app/) | the application (login screen) |
| [https://gs-hackathon-production.up.railway.app/docs](https://gs-hackathon-production.up.railway.app/docs) | interactive API documentation |
| [https://gs-hackathon-production.up.railway.app/health](https://gs-hackathon-production.up.railway.app/health) | health check |

If you deploy your own copy, use the address generated in step 4 in the same way.

**First administrator and sample data**
The database on Railway starts empty. Run the scripts inside the running container, e.g. with the Railway CLI:
```bash
railway ssh
python create_admin.py --uname admin --email admin@example.com --password <your-password>
python seed.py            # optional sample data
```
After that, sign in as the administrator and invite the team (see [Creating your account](#creating-your-account)).

**Updates**
Every push to the connected branch starts a new build and deploy automatically.
The database tables are created and updated on startup, so no manual migration is needed.

---

## Creating your account

Accounts cannot be created freely. Every new user needs a **single-use invite code** from a lead or an administrator,
so only invited people get access.

### 1. The first administrator (once, from the terminal)
The very first account is created on the server:
```bash
python create_admin.py --uname admin --email admin@example.com --password <your-password>
```

### 2. A lead creates an invite code
1. Log in and open the **Lead & Teams** tab.
2. If needed, create the team first (e.g. *Payments*).
3. In the invite section choose:
   - **role:** `member` (regular team member) or `lead` (can approve risky runbook steps and manage the team),
   - **team** (optional): the new user will be placed in this team automatically.
4. Click generate and send the code (format `GS-XXXX-XXXX`) to the new colleague.

### 3. The new user registers
1. Open the application and choose **Register with Code** on the sign-in screen.
2. Fill in:
   - **Username** and **E-mail**,
   - **Password** and **Password confirmation**,
   - **Invite Code**,
   - optionally a **phone number** (needed for SMS and phone calls) and a **team**
     (if the invite code already has a team, that team is used).
3. Click **Complete Registration**.

The code can be used only once. After registration the user automatically appears in the **People** tab
of their team, with the role from the invite.

### 4. After the first login
- Sign in with your username (or e-mail) and password.
- Your phone number and team can be changed later in your profile.
- In **People** you (or your lead) can set your on-call status, channel preferences per severity and quiet hours.

---

## How to use it

1. **Log in** with your account (see [Creating your account](#creating-your-account)).
2. **Lead & Teams** (leads and admins): create teams and generate invite codes for your colleagues.
3. **People:** check team members, their phone numbers, on-call status, channel preferences and quiet hours.
4. **Sources:** add a source (e.g. a webhook) or use one from the seed. Click **Simulate** to generate test events,
   or use the **dry run** playground to check how a payload is parsed.
5. **Rules:** create a rule. Choose the conditions, severity, team, channels and runbook, and test it on a sample event.
6. **Runbooks:** write or paste a runbook (YAML, Markdown, text...) and check the parsed steps in the preview.
7. **Alerts:** watch alerts appear live. Open an alert to see its runbook steps, click **Approve**, **Mark done** or **Retry**,
   and finally **Acknowledge** and **Resolve** it.
8. **Outbox:** see every notification and its delivery status, and reply to SMS on the **Fake phone**.

---

## Demo walkthrough

A short scenario that shows the whole path, from an event to an e-mail in a real inbox.

**Before you start**
- Load the sample data: `python seed.py`.
- To receive the e-mail in a real inbox (e.g. Gmail), set a real SMTP server in `.env`
  (`SMTP_HOST`, `SMTP_PORT`, `SMTP_STARTTLS`, `SMTP_USER`, `SMTP_PASSWORD`).
  With the default settings the e-mail goes to the local Mailpit inbox (`http://localhost:8025`).

**Step 1: Add a person to the team**
1. As a lead, open **Lead & Teams** and generate an invite code with role `member` and team **Payments**.
2. Sign out, choose **Register with Code** and register the demo user with the e-mail address of the inbox you want to use.
3. Sign in again as the lead and open **People**: the new person is in the Payments team.
   The e-mail channel is already selected for **Critical** and **Warning** alerts.

**Step 2: Show how the rule and the source are connected**
- **Rules:** the rule **Critical payments-api alerts** belongs to the Payments team and reacts to error events from `payments-api`.
- **Sources:** the source **payments-webhook** is where these events come in.

**Step 3: Trigger an incident**
1. In **Sources**, click **Simulate** next to `payments-webhook`.
2. Click **Send Simulated Events**. A synthetic error (e.g. HTTP 500 / timeout) is sent into the pipeline.

**Step 4: See the result live**
- **Alerts:** a new critical alert *HighErrorRate on payments-api* appears without refreshing the page.
- **Outbox:** a delivery to the demo user's e-mail address with the status `sent`.
- **Inbox:** a formatted e-mail titled `[CRITICAL] HighErrorRate on payments-api`, with the runbook steps and an **Open alert** button.

---

## Configuration

Settings are read from `.env` (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./app.db` | database; use PostgreSQL in production |
| `SECRET_KEY` | – | key for signing JWT tokens (the same on every server copy) |
| `PORT` | `8000` | HTTP port |
| `APP_URL` | `http://localhost:5173` | base URL for "Open alert" links in e-mails and SMS |
| `EMAIL_PROVIDER` | `smtp` | e-mail channel provider |
| `SMTP_HOST`, `SMTP_PORT` | `localhost`, `1025` | SMTP server (Mailpit by default) |
| `SMTP_STARTTLS`, `SMTP_USER`, `SMTP_PASSWORD` | – | for a real mail server |
| `MAIL_FROM` | `GS Alerting <alerts@gs-alerting.local>` | sender address |
| `SMS_PROVIDER`, `PHONE_PROVIDER` | `fake` | SMS and phone providers |
| `RUNBOOK_ALLOW_REAL_HTTP` | `0` | `1` lets runbook actions make real HTTP calls |

---

## Scaling and deployment

The service is designed to run as **many identical copies** behind a load balancer.
The copies keep no state of their own; everything shared lives in PostgreSQL:

- **Deduplication:** a partial unique index (one open alert per `dedup_key`) plus an atomic
  `INSERT ... ON CONFLICT DO UPDATE`. Tested with 300 parallel events on 3 copies: exactly 1 alert with a count of 300.
- **Live feed:** each copy pushes updates to its browsers over SSE, and copies tell each other about changes with
  PostgreSQL `LISTEN/NOTIFY`. No extra infrastructure such as Redis is needed.
- **Outbox:** a delivery is claimed with one atomic `UPDATE`, so a message is never sent twice.
- **Source workers:** pull-based sources (API polling, SSE, log files) are run by only one copy at a time thanks to
  PostgreSQL advisory locks, with automatic failover. Kafka and RabbitMQ use consumer groups / competing consumers.
- **Runbook steps:** the alert row is locked (`SELECT ... FOR UPDATE`) while steps run, so a step is never run twice.
- Locally the same code falls back to in-memory mode on SQLite, so nothing extra has to be installed.

More details: [SKALOWANIE.md](SKALOWANIE.md) (in Polish).

To run several copies, point all of them to the same PostgreSQL database (`DATABASE_URL`) and use the same `SECRET_KEY`.
On Railway this means increasing the number of replicas of the service. Use `GET /health` for health checks.
For running and deploying the application see [Getting started](#getting-started).

---

## Project structure

```text
.
├── main.py                 app start: database setup, routers, background workers, serving the frontend
├── database.py             database connection and startup lock
├── models.py               database tables (SQLAlchemy)
├── schemas.py              request / response models (Pydantic)
├── seed.py                 optional sample data (CLI)
├── create_admin.py         creates the first administrator (CLI)
├── routers/                REST API endpoints, one file per area
│   ├── alerts.py  rules.py  people.py  sources.py  runbooks.py  deliveries.py
│   └── auth.py  admin.py  api.py  deps.py
├── services/               business logic
│   ├── pipeline.py         the path of one event through the system
│   ├── connectors/         sources, parser, simulator, background ingest workers
│   ├── rules_engine.py     rule matching and templates
│   ├── alert_service.py    alerts and deduplication
│   ├── live.py             live feed (SSE, LISTEN/NOTIFY)
│   ├── runbook_parser.py   turns runbook text into steps
│   ├── runbook_runner.py   runs runbook steps, approvals, conditions
│   ├── simulator.py        safe simulator for runbook actions
│   ├── people_service.py   who gets notified and how
│   ├── delivery.py         outbox and background delivery worker
│   ├── channels/           e-mail, SMS and phone channels
│   └── replies.py          SMS / phone replies (ACK, YES, RESOLVE)
├── frontend/src/           React app, one folder per tab
│   ├── alerts/  rules/  people/  sources/  runbooks/  outbox/
│   └── components/  shared/  services/
├── tests/                  automated tests
├── Dockerfile, render.yaml, start.sh
└── TEAM.md, SKALOWANIE.md  team notes (in Polish)
```

---

## API overview

Full, interactive documentation is available at `/docs` when the backend is running.

| Area | Main endpoints |
|---|---|
| Ingest | `POST /api/ingest/{source_key}`, `GET /api/events` |
| Sources | `/api/sources`, `GET /api/sources/types`, `POST /api/sources/dry-run`, `POST /api/sources/{id}/simulate`, `POST /api/sources/import`, `GET /api/sources/{id}/export` |
| Rules | `/api/rules`, `GET /api/rules/fields`, `POST /api/engine/test` |
| Alerts | `/api/alerts`, `GET /api/alerts/stream`, `POST /api/alerts/{id}/ack`, `POST /api/alerts/{id}/resolve`, `POST /api/alerts/{id}/steps/{idx}/approve`, `POST /api/alerts/{id}/steps/{idx}/done` |
| Runbooks | `/api/runbooks`, `POST /api/runbooks/parse-preview` |
| People & teams | `/api/people`, `POST /api/people/preview`, `GET /api/teams` |
| Outbox & channels | `GET /api/deliveries`, `POST /api/deliveries/test`, `GET /api/channels`, `PUT /api/channels/{channel}/outage`, `POST /api/channels/sms/inbound`, `POST /api/channels/phone/inbound` |
| Auth & admin | `POST /api/auth/register`, `POST /api/auth/login`, `GET/PUT /api/auth/me`, `/api/admin/invites`, `/api/admin/users`, `/api/admin/teams` |
| System | `GET /health` |

---

## Tests

```bash
pytest
```

The tests use temporary SQLite databases and never touch `app.db`. They cover:

- the rules engine, templates and runbook parsing (`test_engine.py`),
- the API and ingest (`test_api.py`),
- the full pipeline from source to outbox, deduplication and approval rules (`test_integration_pipeline.py`),
- e-mail delivery, retries, outages and SMS / phone replies (`test_channels_delivery.py`),
- running runbook steps (`test_runner.py`),
- people, roles, teams and recipient planning (`test_people_service.py`, `test_people_roles.py`, `test_rules_people_api.py`, `test_admin_people_sync.py`),
- the seed command (`test_seed_cli.py`).
