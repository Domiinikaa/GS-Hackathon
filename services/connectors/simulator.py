"""
Built-in realistic event simulator & sample presets (Appendix A + extra scenarios).
Allows simulating every source type (Webhook, Polled API, SSE, Log File, Kafka,
RabbitMQ, Custom) with zero external infrastructure.
"""
from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Any


SIMULATOR_PRESETS: dict[str, dict[str, Any]] = {
    "workflow_failure": {
        "id": "workflow_failure",
        "label": "Workflow Failure",
        "description": "Settlement workflow timeout in prod — matches 'settlements-prod' rule.",
        "format": "json",
        "sample": {
            "type": "WORKFLOW_FAILED",
            "workflowId": "WF-20261121-00042",
            "workflowName": "order-settlement",
            "step": "validate-counterparty",
            "severity": "ERROR",
            "environment": "prod",
            "timestamp": "2026-11-21T00:14:02.331Z",
            "error": {
                "code": "TIMEOUT",
                "message": "Counterparty service did not respond in 5000 ms",
            },
        },
    },
    "metric_breach": {
        "id": "metric_breach",
        "label": "Metric Threshold Breach",
        "description": "Prometheus/Alertmanager-style HTTP webhook — matches 'anna-payments-critical' rule.",
        "format": "json",
        "sample": {
            "alertname": "HighErrorRate",
            "labels": {
                "service": "payments-api",
                "region": "eu-west",
                "severity": "critical",
            },
            "annotations": {
                "summary": "Error rate 12% over the last 5 minutes",
            },
            "startsAt": "2026-11-21T00:13:00Z",
            "status": "firing",
        },
    },
    "trade_rejected": {
        "id": "trade_rejected",
        "label": "Business Event — Trade Rejected",
        "description": "Broker envelope with meta/payload — matches 'rates-big-rejections' rule.",
        "format": "json",
        "sample": {
            "meta": {
                "schema": "trade.rejected.v2",
                "producer": "trade-gateway",
                "ts": 1792833245000,
            },
            "payload": {
                "tradeId": "T-998877",
                "desk": "rates",
                "notional": 25000000,
                "currency": "EUR",
                "reason": "LIMIT_BREACH",
            },
        },
    },
    "pricing_log": {
        "id": "pricing_log",
        "label": "Pricing Engine Log Line",
        "description": "Raw plain-text log line for Tailed Log File — matches 'pricing-warnings' rule.",
        "format": "text",
        "sample": (
            '2026-11-21T00:15:00Z WARN service=pricing-engine-eu1 '
            'instrument=EURUSD latency_ms=1420 message="Cache latency exceeded 1000ms threshold"'
        ),
    },
    "kafka_order_event": {
        "id": "kafka_order_event",
        "label": "Kafka Order Matching Event",
        "description": "Simulated Kafka message with partition/offset envelope.",
        "format": "json",
        "sample": {
            "event_type": "ORDER_LATENCY_SPIKE",
            "service": "matching-engine-ny",
            "environment": "prod",
            "severity": "warning",
            "instrument": "US10Y",
            "latency_ms": 840,
            "venue": "NYSE",
        },
    },
    "statuspage_incident": {
        "id": "statuspage_incident",
        "label": "Polled REST API Incident",
        "description": "External status API / REST incident payload.",
        "format": "json",
        "sample": {
            "id": "inc-98421",
            "name": "Elevated API error rates in eu-west",
            "status": "investigating",
            "impact": "major",
            "service": "clearing-gateway",
            "updated_at": "2026-11-21T00:15:00Z",
        },
    },
}


def list_simulator_presets() -> list[dict[str, Any]]:
    return list(SIMULATOR_PRESETS.values())


def generate_simulated_event(preset_id: str, source_kind: str = "webhook", config: dict[str, Any] | None = None) -> Any:
    """
    Generate a fresh, realistic simulated event for the given preset and source kind.
    Returns a raw string for text presets (e.g. pricing_log) or a dict for JSON presets.
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    cfg = config or {}

    if preset_id == "pricing_log":
        level = random.choice(["WARN", "ERROR", "WARN", "FATAL"])
        node = random.choice(["pricing-engine-eu1", "pricing-engine-us2", "pricing-engine-ap1"])
        instrument = random.choice(["EURUSD", "GBPUSD", "USDJPY", "US10Y", "DE10Y"])
        latency = random.randint(1050, 2800)
        msg = random.choice([
            "Cache latency exceeded 1000ms threshold",
            "Stale market data snapshot detected",
            "Quote publisher queue backpressure",
        ])
        return f'{now_iso} {level} service={node} instrument={instrument} latency_ms={latency} message="{msg}"'

    if preset_id == "workflow_failure":
        event: dict[str, Any] = {
            "type": "WORKFLOW_FAILED",
            "workflowId": f"WF-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{random.randint(10000, 99999)}",
            "workflowName": "order-settlement",
            "step": random.choice(["validate-counterparty", "reserve-collateral", "book-ledger"]),
            "severity": "ERROR",
            "environment": "prod",
            "timestamp": now_iso,
            "error": {
                "code": random.choice(["TIMEOUT", "REJECTED"]),
                "message": f"Counterparty service did not respond in {random.choice([3000, 5000, 8000])} ms",
            },
        }
    elif preset_id == "metric_breach":
        rate = random.randint(8, 28)
        event = {
            "alertname": "HighErrorRate",
            "labels": {
                "service": "payments-api",
                "region": random.choice(["eu-west", "us-east", "ap-south"]),
                "severity": "critical",
            },
            "annotations": {
                "summary": f"Error rate {rate}% over the last 5 minutes",
            },
            "startsAt": now_iso,
            "status": "firing",
        }
    elif preset_id == "trade_rejected":
        event = {
            "meta": {
                "schema": "trade.rejected.v2",
                "producer": "trade-gateway",
                "ts": int(time.time() * 1000),
            },
            "payload": {
                "tradeId": f"T-{random.randint(100000, 999999)}",
                "desk": "rates",
                "notional": random.choice([12500000, 18000000, 25000000, 42000000]),
                "currency": random.choice(["EUR", "USD", "GBP"]),
                "reason": random.choice(["LIMIT_BREACH", "CREDIT_CHECK_FAILED", "INVALID_SETTLEMENT_DATE"]),
            },
        }
    elif preset_id == "statuspage_incident":
        event = {
            "id": f"inc-{random.randint(10000, 99999)}",
            "name": random.choice([
                "Elevated API error rates in eu-west",
                "Degraded settlement throughput",
                "Webhook delivery delays",
            ]),
            "status": random.choice(["investigating", "identified", "monitoring"]),
            "impact": random.choice(["minor", "major", "critical"]),
            "service": random.choice(["clearing-gateway", "payments-api", "fx-bridge"]),
            "updated_at": now_iso,
        }
    else:
        event = {
            "event_type": "ORDER_LATENCY_SPIKE",
            "service": random.choice(["matching-engine-ny", "matching-engine-ldn"]),
            "environment": "prod",
            "severity": random.choice(["warning", "critical"]),
            "instrument": random.choice(["US10Y", "EURUSD", "ESZ6"]),
            "latency_ms": random.randint(450, 2200),
            "timestamp": now_iso,
        }

    # Attach lightweight transport metadata for simulated broker/stream sources
    if source_kind == "kafka":
        event["_kafka"] = {
            "topic": cfg.get("topic") or "trade-events",
            "partition": random.randint(0, 3),
            "offset": random.randint(1000, 99999),
            "simulated": True,
        }
    elif source_kind == "rabbitmq":
        event["_amqp"] = {
            "queue": cfg.get("queue") or "workflow.events",
            "exchange": cfg.get("exchange") or "events.topic",
            "routing_key": cfg.get("routing_key") or "workflow.failed",
            "simulated": True,
        }
    elif source_kind == "sse":
        event["_sse"] = {
            "stream": cfg.get("url") or "simulated://sse-stream",
            "event": "message",
            "simulated": True,
        }

    return event
