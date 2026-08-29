#!/usr/bin/env python3
"""Generate the Codestra corporate Grafana dashboard portfolio.

The generator is deterministic, performs no network calls, reads no secrets, and writes
read-only dashboard JSON from the source-controlled business registry. Queries use only
the canonical Codestra Prometheus/Loki contracts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "codestra" / "business-registry.json"
OUT = ROOT / "codestra" / "dashboards"
PROM_UID = "codestra-prometheus"
LOKI_UID = "codestra-loki"


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")[:40]


def datasource(uid: str, kind: str) -> dict[str, str]:
    return {"type": kind, "uid": uid}


def prom_target(
    expr: str,
    ref: str = "A",
    legend: str = "{{service}}",
    instant: bool = False,
) -> dict[str, Any]:
    return {
        "datasource": datasource(PROM_UID, "prometheus"),
        "editorMode": "code",
        "expr": expr,
        "instant": instant,
        "legendFormat": legend,
        "range": not instant,
        "refId": ref,
    }


def log_target(expr: str, ref: str = "A") -> dict[str, Any]:
    return {
        "datasource": datasource(LOKI_UID, "loki"),
        "editorMode": "code",
        "expr": expr,
        "queryType": "range",
        "refId": ref,
    }


def query_variable(
    name: str,
    label: str,
    query: str,
    ref: str,
    *,
    include_all: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "label": label,
        "type": "query",
        "datasource": datasource(PROM_UID, "prometheus"),
        "definition": query,
        "query": {"query": query, "refId": ref},
        "refresh": 2,
        "sort": 1,
        "multi": True,
        "includeAll": include_all,
        "allValue": ".*" if include_all else None,
    }
    return payload


def constant_variable(name: str, label: str, value: str) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "type": "constant",
        "query": value,
        "current": {"selected": True, "text": value, "value": value},
        "hide": 2,
    }


def templating(
    *,
    fixed_business: str | None = None,
    fixed_service: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    variables: list[dict[str, Any]] = []
    if fixed_business:
        variables.append(
            constant_variable("codestra_business", "Business", fixed_business)
        )
    else:
        variables.append(
            query_variable(
                "codestra_business",
                "Business",
                "label_values(up, codestra_business)",
                "business",
            )
        )

    variables.extend(
        [
            query_variable(
                "environment",
                "Environment",
                'label_values(up{codestra_business=~"$codestra_business"}, environment)',
                "environment",
            ),
            query_variable(
                "region",
                "Region",
                'label_values(up{codestra_business=~"$codestra_business",environment=~"$environment"}, region)',
                "region",
            ),
            query_variable(
                "deployment",
                "Deployment",
                'label_values(up{codestra_business=~"$codestra_business",environment=~"$environment",region=~"$region"}, deployment)',
                "deployment",
            ),
        ]
    )

    if fixed_service:
        variables.append(constant_variable("service", "Service", fixed_service))
    else:
        variables.append(
            query_variable(
                "service",
                "Service",
                'label_values(up{codestra_business=~"$codestra_business",environment=~"$environment",region=~"$region"}, service)',
                "service",
            )
        )
    return {"list": variables}


def metric_selector(
    *,
    fixed_business: str | None = None,
    fixed_service: str | None = None,
    service_regex: str | None = None,
) -> str:
    labels = [
        f'codestra_business="{fixed_business}"'
        if fixed_business
        else 'codestra_business=~"$codestra_business"',
        'environment=~"$environment"',
        'region=~"$region"',
        'deployment=~"$deployment"',
    ]
    if fixed_service:
        labels.append(f'service="{fixed_service}"')
    elif service_regex:
        labels.append(f'service=~"{service_regex}"')
    else:
        labels.append('service=~"$service"')
    return ",".join(labels)


def log_selector(
    *,
    fixed_business: str | None = None,
    fixed_service: str | None = None,
    service_regex: str | None = None,
) -> str:
    # Loki intentionally uses the same bounded corporate dimensions as Prometheus.
    return metric_selector(
        fixed_business=fixed_business,
        fixed_service=fixed_service,
        service_regex=service_regex,
    )


def stat_panel(
    panel_id: int,
    title: str,
    expr: str,
    x: int,
    y: int,
    *,
    unit: str = "short",
    width: int = 6,
    thresholds: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "unit": unit,
        "mappings": [],
        "thresholds": {
            "mode": "absolute",
            "steps": thresholds
            or [
                {"color": "green", "value": None},
                {"color": "red", "value": 1},
            ],
        },
    }
    return {
        "id": panel_id,
        "title": title,
        "type": "stat",
        "datasource": datasource(PROM_UID, "prometheus"),
        "targets": [prom_target(expr, instant=True)],
        "gridPos": {"h": 6, "w": width, "x": x, "y": y},
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {
            "colorMode": "value",
            "graphMode": "area",
            "justifyMode": "auto",
            "orientation": "auto",
            "reduceOptions": {
                "calcs": ["lastNotNull"],
                "fields": "",
                "values": False,
            },
            "textMode": "auto",
        },
    }


def time_series_panel(
    panel_id: int,
    title: str,
    expr: str,
    x: int,
    y: int,
    *,
    unit: str,
    width: int = 12,
    legend: str = "{{service}}",
) -> dict[str, Any]:
    return {
        "id": panel_id,
        "title": title,
        "type": "timeseries",
        "datasource": datasource(PROM_UID, "prometheus"),
        "targets": [prom_target(expr, legend=legend)],
        "gridPos": {"h": 8, "w": width, "x": x, "y": y},
        "fieldConfig": {
            "defaults": {"unit": unit},
            "overrides": [],
        },
        "options": {
            "legend": {
                "calcs": ["lastNotNull", "max", "mean"],
                "displayMode": "table",
                "placement": "bottom",
                "showLegend": True,
            },
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
    }


def table_panel(
    panel_id: int,
    title: str,
    expr: str,
    x: int,
    y: int,
    *,
    width: int = 24,
    legend: str = "{{codestra_business}} / {{service}} / {{deployment}}",
) -> dict[str, Any]:
    return {
        "id": panel_id,
        "title": title,
        "type": "table",
        "datasource": datasource(PROM_UID, "prometheus"),
        "targets": [prom_target(expr, legend=legend, instant=True)],
        "gridPos": {"h": 7, "w": width, "x": x, "y": y},
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {"cellHeight": "sm", "showHeader": True},
    }


def logs_panel(
    panel_id: int,
    title: str,
    expr: str,
    x: int,
    y: int,
    *,
    height: int = 10,
) -> dict[str, Any]:
    return {
        "id": panel_id,
        "title": title,
        "type": "logs",
        "datasource": datasource(LOKI_UID, "loki"),
        "targets": [log_target(expr)],
        "gridPos": {"h": height, "w": 24, "x": x, "y": y},
        "options": {
            "dedupStrategy": "signature",
            "enableLogDetails": True,
            "prettifyLogMessage": False,
            "showCommonLabels": False,
            "showLabels": False,
            "showTime": True,
            "sortOrder": "Descending",
            "wrapLogMessage": True,
        },
    }


def standard_dashboard(
    *,
    title: str,
    uid: str,
    tags: list[str],
    fixed_business: str | None = None,
    fixed_service: str | None = None,
    service_regex: str | None = None,
) -> dict[str, Any]:
    selector = metric_selector(
        fixed_business=fixed_business,
        fixed_service=fixed_service,
        service_regex=service_regex,
    )
    logs = log_selector(
        fixed_business=fixed_business,
        fixed_service=fixed_service,
        service_regex=service_regex,
    )

    panels = [
        stat_panel(
            1,
            "Target availability",
            f"100 * avg(up{{{selector}}})",
            0,
            0,
            unit="percent",
            thresholds=[
                {"color": "red", "value": None},
                {"color": "orange", "value": 99.0},
                {"color": "green", "value": 99.9},
            ],
        ),
        stat_panel(
            2,
            "Firing alerts",
            f'sum(ALERTS{{alertstate="firing",{selector}}})',
            6,
            0,
            unit="short",
        ),
        stat_panel(
            3,
            "Request rate",
            f"sum(codestra:http_requests:rate5m{{{selector}}})",
            12,
            0,
            unit="reqps",
        ),
        stat_panel(
            4,
            "5xx error ratio",
            f"100 * max(codestra:http_error_ratio:5m{{{selector}}})",
            18,
            0,
            unit="percent",
            thresholds=[
                {"color": "green", "value": None},
                {"color": "orange", "value": 1.0},
                {"color": "red", "value": 5.0},
            ],
        ),
        time_series_panel(
            5,
            "Traffic by service",
            f"sum by (service) (codestra:http_requests:rate5m{{{selector}}})",
            0,
            6,
            unit="reqps",
        ),
        time_series_panel(
            6,
            "p95 request latency",
            f"max by (service) (codestra:http_duration_seconds:p95_5m{{{selector}}})",
            12,
            6,
            unit="s",
        ),
        time_series_panel(
            7,
            "SLO error-budget burn rate",
            f"max by (service) (codestra:slo_http_burn_rate:5m{{{selector}}})",
            0,
            14,
            unit="short",
        ),
        time_series_panel(
            8,
            "Queue and delivery backlog",
            (
                f"max by (service) (codestra:outbox_backlog:max{{{selector}}}) "
                f"or max by (service) (codestra:inbox_backlog:max{{{selector}}}) "
                f"or max by (service) (codestra:queue_depth:max{{{selector}}})"
            ),
            12,
            14,
            unit="short",
        ),
        table_panel(
            9,
            "Active incidents",
            (
                "sum by (alertname, severity, codestra_business, service, "
                f'environment, region, deployment) (ALERTS{{alertstate="firing",{selector}}})'
            ),
            0,
            22,
            legend="{{severity}} / {{alertname}} / {{codestra_business}} / {{service}}",
        ),
        table_panel(
            10,
            "Current deployment and version evidence",
            f"codestra:deployment_info:max{{{selector}}}",
            0,
            29,
        ),
        logs_panel(
            11,
            "Redacted error and security context",
            (
                f'{{{logs}}} | json | '
                '(level=~"error|critical" or event_family=~"security|authorization|reconciliation")'
            ),
            0,
            36,
        ),
        logs_panel(
            12,
            "What changed: deployment, configuration, and feature state",
            (
                f'{{{logs}}} | json | '
                'event_family=~"deployment|configuration|feature_flag|capability"'
            ),
            0,
            46,
            height=8,
        ),
    ]

    return {
        "annotations": {
            "list": [
                {
                    "builtIn": 1,
                    "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                    "enable": True,
                    "hide": True,
                    "iconColor": "rgba(0, 211, 255, 1)",
                    "name": "Annotations and alerts",
                    "type": "dashboard",
                }
            ]
        },
        "description": (
            "Codestra corporate operational view using bounded business, service, "
            "environment, region, and deployment dimensions. No business mutation "
            "or customer-level data authority is provided."
        ),
        "editable": False,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "liveNow": False,
        "panels": panels,
        "refresh": "30s",
        "schemaVersion": 39,
        "tags": ["codestra", "corporate", *tags],
        "templating": templating(
            fixed_business=fixed_business,
            fixed_service=fixed_service,
        ),
        "time": {"from": "now-6h", "to": "now"},
        "timepicker": {
            "refresh_intervals": ["30s", "1m", "5m", "15m", "30m", "1h"],
            "time_options": ["15m", "1h", "6h", "12h", "24h", "2d", "7d", "30d"],
        },
        "timezone": "browser",
        "title": title,
        "uid": uid,
        "version": 1,
        "weekStart": "monday",
    }


def write(folder: str, filename: str, payload: dict[str, Any]) -> None:
    path = OUT / folder / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def generate_special() -> None:
    write(
        "incident",
        "incident-triage.json",
        standard_dashboard(
            title="Incident Triage — What broke, where, who is affected, what changed?",
            uid="codestra-incident-triage",
            tags=["incident", "triage"],
        ),
    )
    write(
        "executive",
        "executive-platform.json",
        standard_dashboard(
            title="Executive Platform Health",
            uid="codestra-executive-platform",
            tags=["executive", "platform"],
        ),
    )

    core = [
        ("platform", "infrastructure-health", "Infrastructure Health", "node-exporter|cadvisor|alloy"),
        ("platform", "middleware-transactions", "Middleware Transactions", "middleware"),
        ("api", "kong-api-gateway", "Kong API Gateway", "kong"),
        ("security", "keycloak-authentication", "Keycloak Authentication", "keycloak"),
        ("platform", "odoo-integration", "Odoo Health and Integration", "odoo"),
        ("platform", "n8n-workflows", "n8n Workflow Health", "n8n"),
        ("contact-center", "vicidial-call-center", "VICIdial Call Center", "vicidial"),
        ("database", "postgres", "PostgreSQL Health", "postgres-exporter"),
        ("database", "redis", "Redis Health", "redis-exporter"),
        ("platform", "caddy-edge", "Caddy Edge", "caddy"),
        ("deployment", "deployment-version", "Deployment and Version", ".+"),
        ("security", "security-events", "Security Events", "keycloak|kong|openbao|middleware"),
        ("slo", "error-budget", "SLO and Error Budget", ".+"),
        ("environment", "environment-health", "Environment Health", ".+"),
        ("server", "server-health", "Server and Container Health", "node-exporter|cadvisor|alloy"),
    ]
    for folder, stem, title, services in core:
        write(
            folder,
            f"{stem}.json",
            standard_dashboard(
                title=title,
                uid=f"codestra-{slug(stem)}",
                tags=[folder, stem],
                fixed_business="platform",
                service_regex=services,
            ),
        )


def main() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if OUT.exists():
        for path in OUT.rglob("*.json"):
            path.unlink()

    generate_special()
    for business in registry["businesses"]:
        business_id = business["id"]
        display_name = business["display_name"]
        write(
            "business",
            f"business-{slug(business_id)}.json",
            standard_dashboard(
                title=f"{display_name} — Business Health",
                uid=f"biz-{slug(business_id)}",
                tags=["business", business_id, business.get("service_tier", "unclassified")],
                fixed_business=business_id,
            ),
        )
        for app in business["repositories"]:
            service = app["service"]
            write(
                "business",
                f"app-{slug(service)}.json",
                standard_dashboard(
                    title=f"{display_name} — {service}",
                    uid=f"app-{slug(service)}",
                    tags=["application", business_id, app["profile"]],
                    fixed_business=business_id,
                    fixed_service=service,
                ),
            )

    generated = sorted(OUT.rglob("*.json"))
    print(f"generated {len(generated)} dashboards under {OUT}")


if __name__ == "__main__":
    main()
