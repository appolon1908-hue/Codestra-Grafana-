#!/usr/bin/env python3
"""Generate Codestra Grafana dashboards from the authoritative business registry.

No network access, credentials, or runtime writes are used. Generated dashboards are
plain JSON and are intended to be provisioned read-only by Grafana.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "codestra" / "business-registry.json"
OUT = ROOT / "codestra" / "dashboards"
PROM_UID = "codestra-prometheus"
LOKI_UID = "codestra-loki"


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")[:40]


def ds(uid: str, typ: str) -> dict:
    return {"type": typ, "uid": uid}


def prom_target(expr: str, ref: str = "A", legend: str = "{{service}}") -> dict:
    return {"datasource": ds(PROM_UID, "prometheus"), "expr": expr, "legendFormat": legend, "refId": ref}


def log_target(expr: str, ref: str = "A") -> dict:
    return {"datasource": ds(LOKI_UID, "loki"), "expr": expr, "queryType": "range", "refId": ref}


def common_vars() -> dict:
    return {
        "list": [
            {
                "name": "environment",
                "label": "Environment",
                "type": "query",
                "datasource": ds(PROM_UID, "prometheus"),
                "query": {"query": "label_values(up{codestra_managed=\"true\"}, environment)", "refId": "env"},
                "includeAll": True,
                "allValue": ".*",
                "multi": True,
                "refresh": 2,
            }
        ]
    }


def standard_dashboard(title: str, uid: str, prom_selector: str, loki_selector: str, tags: list[str]) -> dict:
    return {
        "annotations": {"list": []},
        "editable": False,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "panels": [
            {
                "id": 1,
                "title": "Targets down",
                "type": "stat",
                "datasource": ds(PROM_UID, "prometheus"),
                "targets": [prom_target(f"sum(up{{codestra_managed=\"true\",environment=~\"$environment\",{prom_selector}}} == 0)")],
                "gridPos": {"h": 6, "w": 6, "x": 0, "y": 0},
                "fieldConfig": {"defaults": {"unit": "short"}, "overrides": []},
                "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "orientation": "auto"},
            },
            {
                "id": 2,
                "title": "HTTP 5xx rate",
                "type": "timeseries",
                "datasource": ds(PROM_UID, "prometheus"),
                "targets": [prom_target(f"sum by (service) (rate(http_server_requests_total{{environment=~\"$environment\",status=~\"5..\",{prom_selector}}}[5m]))", legend="{{service}}")],
                "gridPos": {"h": 8, "w": 18, "x": 6, "y": 0},
                "fieldConfig": {"defaults": {"unit": "reqps"}, "overrides": []},
                "options": {"legend": {"displayMode": "table", "placement": "bottom"}},
            },
            {
                "id": 3,
                "title": "Current deployment markers",
                "type": "table",
                "datasource": ds(PROM_UID, "prometheus"),
                "targets": [prom_target(f"codestra_build_info{{environment=~\"$environment\",{prom_selector}}}", legend="{{service}} {{version}} {{git_sha}}")],
                "gridPos": {"h": 7, "w": 24, "x": 0, "y": 8},
                "fieldConfig": {"defaults": {}, "overrides": []},
                "options": {"showHeader": True},
            },
            {
                "id": 4,
                "title": "Errors and affected tenant/customer context",
                "type": "logs",
                "datasource": ds(LOKI_UID, "loki"),
                "targets": [log_target(f"{{{loki_selector},environment=~\"$environment\"}} | json | level=~\"error|critical\"")],
                "gridPos": {"h": 10, "w": 24, "x": 0, "y": 15},
                "options": {"showTime": True, "wrapLogMessage": True, "prettifyLogMessage": False, "enableLogDetails": True},
            },
            {
                "id": 5,
                "title": "What changed: deployment/config events",
                "type": "logs",
                "datasource": ds(LOKI_UID, "loki"),
                "targets": [log_target(f"{{{loki_selector},environment=~\"$environment\"}} | json | event=~\"deployment|config_change|feature_flag_change\"")],
                "gridPos": {"h": 8, "w": 24, "x": 0, "y": 25},
                "options": {"showTime": True, "wrapLogMessage": True, "prettifyLogMessage": False, "enableLogDetails": True},
            },
        ],
        "refresh": "30s",
        "schemaVersion": 39,
        "tags": ["codestra", *tags],
        "templating": common_vars(),
        "time": {"from": "now-6h", "to": "now"},
        "timepicker": {},
        "timezone": "browser",
        "title": title,
        "uid": uid,
        "version": 1,
    }


def write(folder: str, filename: str, payload: dict) -> None:
    path = OUT / folder / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def generate_special() -> None:
    write("incident", "incident-triage.json", standard_dashboard(
        "Incident Triage — What broke, where, who is affected, what changed?",
        "codestra-incident-triage",
        'codestra_business=~".+"',
        'codestra_managed="true"',
        ["incident", "triage"],
    ))
    write("executive", "executive-platform.json", standard_dashboard(
        "Executive Platform Health",
        "codestra-executive-platform",
        'codestra_business=~".+"',
        'codestra_managed="true"',
        ["executive", "platform"],
    ))

    core = [
        ("platform", "infrastructure-health", "Infrastructure Health", ".+"),
        ("platform", "middleware-transactions", "Middleware Transactions", "middleware"),
        ("api", "kong-api-gateway", "Kong API Gateway", "kong"),
        ("security", "keycloak-authentication", "Keycloak Authentication", "keycloak"),
        ("platform", "odoo-integration", "Odoo Health and Integration", "odoo"),
        ("platform", "n8n-workflows", "n8n Workflow Health", "n8n"),
        ("contact-center", "vicidial-call-center", "VICIdial Call Center", "vicidial"),
        ("database", "postgres", "PostgreSQL Health", "postgres.*"),
        ("database", "redis", "Redis Health", "redis.*"),
        ("platform", "caddy-edge", "Caddy Edge", "caddy"),
        ("deployment", "deployment-version", "Deployment and Version", ".+"),
        ("security", "security-events", "Security Events", "keycloak|kong|openbao|middleware"),
        ("slo", "error-budget", "SLO and Error Budget", ".+"),
        ("environment", "environment-health", "Environment Health", ".+"),
        ("server", "server-health", "Server and Container Health", "node-exporter|cadvisor|alloy"),
    ]
    for folder, stem, title, services in core:
        write(folder, f"{stem}.json", standard_dashboard(
            title,
            f"codestra-{slug(stem)}",
            f'service=~"{services}"',
            f'service=~"{services}"',
            [folder, stem],
        ))


def main() -> None:
    data = json.loads(REGISTRY.read_text())
    if OUT.exists():
        for path in OUT.rglob("*.json"):
            path.unlink()
    generate_special()
    for business in data["businesses"]:
        bid = business["id"]
        title = business["display_name"]
        write("business", f"business-{slug(bid)}.json", standard_dashboard(
            f"{title} — Business Health",
            f"biz-{slug(bid)}",
            f'codestra_business="{bid}"',
            f'codestra_business="{bid}"',
            ["business", bid],
        ))
        for app in business["repositories"]:
            service = app["service"]
            write("business", f"app-{slug(service)}.json", standard_dashboard(
                f"{title} — {service}",
                f"app-{slug(service)}",
                f'service="{service}"',
                f'service="{service}"',
                ["application", bid, app["profile"]],
            ))
    count = len(list(OUT.rglob("*.json")))
    print(f"generated {count} dashboards under {OUT}")


if __name__ == "__main__":
    main()
