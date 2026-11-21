"""
Declarative Connector Specification Registry.

Each source kind declares its metadata and `config_schema` so the UI can
dynamically render configuration forms without hardcoding per-connector UI.
Adding a new source kind requires only registering a new ConnectorTypeSpec here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


SECRET_MASK = "********"


@dataclass
class FieldSpec:
    name: str
    label: str
    type: str = "string"  # string | number | boolean | select | secret | json | text
    required: bool = False
    default: Any = None
    placeholder: str = ""
    description: str = ""
    options: list[str] = field(default_factory=list)
    group: str = "connection"  # connection | simulation | parsing


@dataclass
class ConnectorTypeSpec:
    kind: str
    label: str
    mode: str  # push | pull | stream
    description: str
    icon: str
    supports_simulation: bool = True
    config_schema: list[FieldSpec] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _simulation_fields(default_simulate: bool = False, default_preset: str = "workflow_failure") -> list[FieldSpec]:
    return [
        FieldSpec(
            name="simulate",
            label="Simulation Mode",
            type="boolean",
            default=default_simulate,
            description="Generate realistic synthetic events in-process without needing an external broker/server.",
            group="simulation",
        ),
        FieldSpec(
            name="sim_preset",
            label="Simulation Scenario",
            type="select",
            default=default_preset,
            options=[
                "workflow_failure",
                "metric_breach",
                "trade_rejected",
                "pricing_log",
                "kafka_order_event",
                "statuspage_incident",
            ],
            description="Event template used when Simulation Mode is active.",
            group="simulation",
        ),
        FieldSpec(
            name="sim_interval_s",
            label="Simulation Interval (s)",
            type="number",
            default=10,
            placeholder="10",
            description="How often a simulated event is emitted while enabled.",
            group="simulation",
        ),
    ]


CONNECTOR_REGISTRY: dict[str, ConnectorTypeSpec] = {
    "webhook": ConnectorTypeSpec(
        kind="webhook",
        label="HTTP Webhook",
        mode="push",
        description="Receive JSON, NDJSON, or plain-text logs via POST /api/ingest/{key}.",
        icon="webhook",
        supports_simulation=True,
        config_schema=[
            FieldSpec(
                name="auth_mode",
                label="Authentication Mode",
                type="select",
                default="none",
                options=["none", "api_key", "bearer", "hmac_sha256"],
                description="Optional inbound authentication checked on /api/ingest/{key}.",
            ),
            FieldSpec(
                name="auth_header",
                label="Auth Header Name",
                type="string",
                default="X-API-Key",
                placeholder="X-API-Key or X-Hub-Signature-256",
                description="Header inspected when auth_mode is api_key or hmac_sha256.",
            ),
            FieldSpec(
                name="auth_secret",
                label="Auth Secret / Token",
                type="secret",
                default="",
                placeholder="Enter secret token...",
                description="Shared secret, bearer token, or HMAC signing key.",
            ),
            FieldSpec(
                name="sim_preset",
                label="Default Test Event Preset",
                type="select",
                default="metric_breach",
                options=[
                    "metric_breach",
                    "workflow_failure",
                    "trade_rejected",
                    "pricing_log",
                    "kafka_order_event",
                    "statuspage_incident",
                ],
                description="Default scenario when clicking Simulate Event.",
                group="simulation",
            ),
        ],
    ),
    "polled_api": ConnectorTypeSpec(
        kind="polled_api",
        label="Polled REST API",
        mode="pull",
        description="Periodically poll an HTTP/REST JSON endpoint with cursor deduplication.",
        icon="globe",
        supports_simulation=True,
        config_schema=[
            FieldSpec(
                name="url",
                label="Endpoint URL",
                type="string",
                required=False,
                placeholder="https://www.githubstatus.com/api/v2/incidents.json",
                description="REST API URL to poll (optional when Simulation Mode is enabled).",
            ),
            FieldSpec(
                name="method",
                label="HTTP Method",
                type="select",
                default="GET",
                options=["GET", "POST"],
                description="HTTP verb used for polling.",
            ),
            FieldSpec(
                name="interval_s",
                label="Poll Interval (s)",
                type="number",
                default=30,
                placeholder="30",
                description="Seconds between polling requests.",
            ),
            FieldSpec(
                name="headers_json",
                label="HTTP Headers (JSON)",
                type="json",
                default={},
                placeholder='{"Authorization": "Bearer ..."}',
                description="Custom request headers as a JSON object.",
            ),
            FieldSpec(
                name="records_path",
                label="Records Array Path",
                type="string",
                default="",
                placeholder="incidents or data.items",
                description="Dot-path to the list of events inside the JSON response (leave blank if response is a list or single object).",
            ),
            FieldSpec(
                name="cursor_field",
                label="Deduplication ID Field",
                type="string",
                default="id",
                placeholder="id",
                description="Field name used to skip records already ingested in previous polls.",
            ),
            FieldSpec(
                name="timeout_s",
                label="Request Timeout (s)",
                type="number",
                default=10,
                placeholder="10",
            ),
            *_simulation_fields(default_simulate=False, default_preset="statuspage_incident"),
        ],
    ),
    "sse": ConnectorTypeSpec(
        kind="sse",
        label="SSE Event Stream",
        mode="stream",
        description="Subscribe to a live Server-Sent Events (text/event-stream) JSON feed.",
        icon="radio",
        supports_simulation=True,
        config_schema=[
            FieldSpec(
                name="url",
                label="SSE Stream URL",
                type="string",
                required=False,
                placeholder="https://stream.wikimedia.org/v2/stream/recentchange",
                description="Live Server-Sent Events endpoint URL.",
            ),
            FieldSpec(
                name="headers_json",
                label="HTTP Headers (JSON)",
                type="json",
                default={},
                placeholder='{"Accept": "text/event-stream"}',
                description="Optional custom headers for the stream connection.",
            ),
            FieldSpec(
                name="max_events_per_min",
                label="Rate Limit (events/min)",
                type="number",
                default=30,
                placeholder="30",
                description="Safety cap to prevent high-volume public streams from flooding local storage.",
            ),
            *_simulation_fields(default_simulate=False, default_preset="metric_breach"),
        ],
    ),
    "logfile": ConnectorTypeSpec(
        kind="logfile",
        label="Tailed Log File",
        mode="pull",
        description="Continuously tail a local log file (JSON lines or plain-text via Regex).",
        icon="file-text",
        supports_simulation=True,
        config_schema=[
            FieldSpec(
                name="file_path",
                label="Log File Path",
                type="string",
                default="/tmp/gs-pricing-engine.log",
                placeholder="/var/log/app/pricing-engine.log",
                description="Absolute path to the log file to tail. In simulation mode, synthetic lines are appended to this file.",
            ),
            FieldSpec(
                name="from_beginning",
                label="Read From Beginning",
                type="boolean",
                default=False,
                description="If enabled, ingests existing lines on startup instead of only newly appended lines.",
            ),
            FieldSpec(
                name="poll_interval_s",
                label="Tail Check Interval (s)",
                type="number",
                default=2,
                placeholder="2",
                description="How frequently to check the file for newly appended lines.",
            ),
            *_simulation_fields(default_simulate=False, default_preset="pricing_log"),
        ],
    ),
    "kafka": ConnectorTypeSpec(
        kind="kafka",
        label="Apache Kafka",
        mode="stream",
        description="Consume events from a Kafka topic (supports real brokers via aiokafka or built-in simulation).",
        icon="layers",
        supports_simulation=True,
        config_schema=[
            FieldSpec(
                name="bootstrap_servers",
                label="Bootstrap Servers",
                type="string",
                default="localhost:9092",
                placeholder="broker1:9092,broker2:9092",
                description="Comma-separated Kafka broker addresses.",
            ),
            FieldSpec(
                name="topic",
                label="Topic Name",
                type="string",
                default="trade-events",
                placeholder="trade-events",
                description="Kafka topic to subscribe to.",
            ),
            FieldSpec(
                name="group_id",
                label="Consumer Group ID",
                type="string",
                default="gs-alerting-consumer",
                placeholder="gs-alerting-consumer",
            ),
            FieldSpec(
                name="security_protocol",
                label="Security Protocol",
                type="select",
                default="PLAINTEXT",
                options=["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"],
            ),
            FieldSpec(
                name="sasl_username",
                label="SASL Username",
                type="string",
                default="",
                placeholder="Optional SASL username",
            ),
            FieldSpec(
                name="sasl_password",
                label="SASL Password",
                type="secret",
                default="",
                placeholder="Optional SASL password",
            ),
            FieldSpec(
                name="auto_offset_reset",
                label="Auto Offset Reset",
                type="select",
                default="latest",
                options=["latest", "earliest"],
            ),
            *_simulation_fields(default_simulate=False, default_preset="trade_rejected"),
        ],
    ),
    "rabbitmq": ConnectorTypeSpec(
        kind="rabbitmq",
        label="RabbitMQ / AMQP",
        mode="stream",
        description="Consume messages from a RabbitMQ queue (supports real AMQP via aio-pika or built-in simulation).",
        icon="mail",
        supports_simulation=True,
        config_schema=[
            FieldSpec(
                name="amqp_url",
                label="AMQP Connection URL",
                type="secret",
                default="amqp://guest:guest@localhost:5672/",
                placeholder="amqp://user:pass@host:5672/vhost",
                description="Full AMQP connection URI.",
            ),
            FieldSpec(
                name="queue",
                label="Queue Name",
                type="string",
                default="workflow.events",
                placeholder="workflow.events",
            ),
            FieldSpec(
                name="exchange",
                label="Exchange (optional)",
                type="string",
                default="",
                placeholder="events.topic",
            ),
            FieldSpec(
                name="routing_key",
                label="Routing Key (optional)",
                type="string",
                default="#",
                placeholder="workflow.*",
            ),
            *_simulation_fields(default_simulate=False, default_preset="workflow_failure"),
        ],
    ),
    "custom": ConnectorTypeSpec(
        kind="custom",
        label="Custom / Universal Spec",
        mode="push",
        description="Define any custom source specification (JSON/YAML metadata, push ingest, or simulated stream).",
        icon="sliders",
        supports_simulation=True,
        config_schema=[
            FieldSpec(
                name="protocol_name",
                label="Protocol / System Name",
                type="string",
                default="syslog-udp",
                placeholder="e.g. gRPC, NATS, Redis Stream, Syslog",
                description="Human-readable label describing this custom integration.",
            ),
            FieldSpec(
                name="custom_spec_json",
                label="Custom Specification (JSON)",
                type="json",
                default={},
                placeholder='{"endpoint": "nats://localhost:4222", "subject": "alerts.>"}',
                description="Arbitrary connection/integration parameters stored with this source.",
            ),
            *_simulation_fields(default_simulate=False, default_preset="kafka_order_event"),
        ],
    ),
}


def get_connector_spec(kind: str) -> Optional[ConnectorTypeSpec]:
    return CONNECTOR_REGISTRY.get(kind)


def list_connector_specs() -> list[dict[str, Any]]:
    return [spec.to_dict() for spec in CONNECTOR_REGISTRY.values()]


def _secret_field_names(kind: str) -> set[str]:
    spec = CONNECTOR_REGISTRY.get(kind)
    if not spec:
        return set()
    return {f.name for f in spec.config_schema if f.type == "secret"}


def mask_source_config(kind: str, config: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Return a copy of config with secret fields masked and internal keys hidden."""
    if not isinstance(config, dict):
        return {}
    masked = {k: v for k, v in config.items() if not str(k).startswith("_")}
    for key in _secret_field_names(kind):
        val = masked.get(key)
        if isinstance(val, str) and val.strip():
            masked[key] = SECRET_MASK
    return masked


def merge_secret_fields(
    kind: str,
    existing_config: Optional[dict[str, Any]],
    incoming_config: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Preserve existing secrets and internal state keys when the UI sends updates."""
    merged = dict(incoming_config or {})
    old = existing_config or {}
    for key in _secret_field_names(kind):
        if merged.get(key) == SECRET_MASK and key in old:
            merged[key] = old[key]
    for key, val in old.items():
        if str(key).startswith("_") and key not in merged:
            merged[key] = val
    return merged


def validate_source_config(kind: str, config: Optional[dict[str, Any]]) -> list[str]:
    """Validate incoming source configuration against its connector spec."""
    errors: list[str] = []
    spec = CONNECTOR_REGISTRY.get(kind)
    if not spec:
        return [f"Unsupported source kind '{kind}'. Allowed: {', '.join(CONNECTOR_REGISTRY.keys())}"]

    cfg = config or {}
    simulate = bool(cfg.get("simulate", False))

    for field_spec in spec.config_schema:
        if field_spec.required and not simulate:
            val = cfg.get(field_spec.name)
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append(f"Missing required field '{field_spec.name}' for kind '{kind}'.")

    if kind in ("polled_api", "sse") and not simulate:
        url = str(cfg.get("url") or "").strip()
        if not url:
            errors.append(f"Field 'url' is required for '{kind}' when Simulation Mode is disabled.")
        elif not (url.startswith("http://") or url.startswith("https://")):
            errors.append("Field 'url' must start with http:// or https://.")

    return errors
