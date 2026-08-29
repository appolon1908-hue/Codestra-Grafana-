#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "codestra" / "business-registry.json"
INI = ROOT / "codestra" / "config" / "grafana.ini"
DATASOURCES = ROOT / "codestra" / "provisioning" / "datasources" / "codestra.yml"
DASHBOARD_PROVISIONING = ROOT / "codestra" / "provisioning" / "dashboards" / "codestra.yml"
RBAC = ROOT / "codestra" / "rbac-policy.json"
DASHBOARDS = ROOT / "codestra" / "dashboards"

ALLOWED_MEDIA_HOSTS = {
    "graf.codestra.media",
    "prom.codestra.media",
    "aler.codestra.media",
    "loki.codestra.media",
    "temp.codestra.media",
    "otel.codestra.media",
    "supe.codestra.media",
    "node.codestra.media",
    "cadv.codestra.media",
    "pgex.codestra.media",
    "rdex.codestra.media",
    "blac.codestra.media",
    "allo.codestra.media",
    "bao.codestra.media",
}
REQUIRED_BUSINESSES = {
    "codestra", "moneybee", "beyvra", "breero", "larim-a", "transportation",
    "booked4seasons", "social", "klyrow", "telnexa", "kyqra", "restaurant", "provisioning",
}
REQUIRED_SERVICES = {"caddy", "kong", "keycloak", "middleware", "odoo", "n8n", "vicidial"}
REQUIRED_DATASOURCES = {
    "https://prom.codestra.media",
    "https://loki.codestra.media",
    "https://temp.codestra.media",
    "https://aler.codestra.media",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def validate_registry() -> dict:
    data = json.loads(REGISTRY.read_text())
    business_ids = [b["id"] for b in data["businesses"]]
    if len(business_ids) != len(set(business_ids)):
        fail("duplicate business ids")
    if not REQUIRED_BUSINESSES.issubset(business_ids):
        fail(f"missing businesses: {sorted(REQUIRED_BUSINESSES - set(business_ids))}")

    repos: list[str] = []
    services: list[str] = []
    for business in data["businesses"]:
        if not business.get("repositories"):
            fail(f"business {business['id']} has no repositories")
        for app in business["repositories"]:
            repos.append(app["repo"])
            services.append(app["service"])
            if app["profile"] not in {"frontend", "backend", "fullstack"}:
                fail(f"invalid profile for {app['repo']}")
    if len(repos) != len(set(repos)):
        fail("a runtime repository is assigned to more than one business")
    if len(services) != len(set(services)):
        fail("duplicate canonical service names")

    platform_services = {item["service"] for item in data["platform_services"]}
    if not REQUIRED_SERVICES.issubset(platform_services):
        fail(f"missing platform services: {sorted(REQUIRED_SERVICES - platform_services)}")
    return data


def validate_config() -> None:
    ini = INI.read_text()
    if "domain = graf.codestra.media" not in ini or "root_url = https://graf.codestra.media" not in ini:
        fail("Grafana canonical hostname is not locked")
    if "auth.codestra.co/realms/codestra" not in ini:
        fail("canonical Keycloak realm is not configured")
    if "client_secret = $__file{" not in ini:
        fail("OAuth client secret must be file-injected, not committed")

    datasources = DATASOURCES.read_text()
    for url in REQUIRED_DATASOURCES:
        if url not in datasources:
            fail(f"missing canonical datasource URL {url}")
    for uid in ("codestra-prometheus", "codestra-loki", "codestra-tempo", "codestra-alertmanager"):
        if uid not in datasources:
            fail(f"missing datasource uid {uid}")
    if "exemplarTraceIdDestinations" not in datasources or "tracesToLogsV2" not in datasources:
        fail("metrics/logs/traces correlation is incomplete")

    dashboard_provisioning = DASHBOARD_PROVISIONING.read_text()
    for folder_uid in (
        "codestra-executive", "codestra-incident", "codestra-platform", "codestra-business",
        "codestra-environment", "codestra-server", "codestra-database", "codestra-api",
        "codestra-security", "codestra-contact-center", "codestra-deployment", "codestra-slo",
    ):
        if folder_uid not in dashboard_provisioning:
            fail(f"missing provisioned folder {folder_uid}")

    rbac = json.loads(RBAC.read_text())
    if rbac.get("default_org_role") != "Viewer":
        fail("normal users must default to Viewer")
    if rbac.get("oauth_role_groups", {}).get("grafana-admin") != "Admin":
        fail("admin OAuth role mapping missing")
    if rbac.get("oauth_role_groups", {}).get("grafana-editor") != "Editor":
        fail("editor OAuth role mapping missing")


def validate_hostnames() -> None:
    pattern = re.compile(r"(?<![A-Za-z0-9.-])([a-z0-9-]+\.codestra\.media)(?![A-Za-z0-9.-])")
    for root in (ROOT / "codestra", ROOT / "scripts"):
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".woff", ".woff2"}:
                continue
            text = path.read_text(errors="ignore")
            for host in pattern.findall(text):
                if host not in ALLOWED_MEDIA_HOSTS:
                    fail(f"alternate/unassigned codestra.media hostname {host} in {path.relative_to(ROOT)}")


def validate_generated_dashboards(data: dict) -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_codestra_dashboards.py")], check=True)
    files = sorted(DASHBOARDS.rglob("*.json"))
    expected_minimum = 2 + 15 + len(data["businesses"]) + sum(len(b["repositories"]) for b in data["businesses"])
    if len(files) < expected_minimum:
        fail(f"generated only {len(files)} dashboards; expected at least {expected_minimum}")

    uids: set[str] = set()
    titles: set[str] = set()
    for path in files:
        dashboard = json.loads(path.read_text())
        uid = dashboard.get("uid")
        title = dashboard.get("title")
        if not uid or uid in uids:
            fail(f"missing/duplicate dashboard uid in {path}")
        if not title or title in titles:
            fail(f"missing/duplicate dashboard title in {path}")
        uids.add(uid)
        titles.add(title)
        if dashboard.get("editable") is not False:
            fail(f"provisioned dashboard must be read-only: {path}")
        serialized = json.dumps(dashboard)
        if re.search(r"tenant_id\\s*[=~]", serialized):
            fail(f"tenant_id must not be used as a metrics/log-stream label selector: {path}")

    required_titles = {
        "Executive Platform Health",
        "Incident Triage — What broke, where, who is affected, what changed?",
        "Infrastructure Health",
        "Middleware Transactions",
        "Kong API Gateway",
        "Keycloak Authentication",
        "Odoo Health and Integration",
        "n8n Workflow Health",
        "VICIdial Call Center",
        "PostgreSQL Health",
        "Redis Health",
        "Caddy Edge",
        "Deployment and Version",
        "Security Events",
        "SLO and Error Budget",
    }
    if not required_titles.issubset(titles):
        fail(f"missing required dashboards: {sorted(required_titles - titles)}")


def main() -> None:
    data = validate_registry()
    validate_config()
    validate_hostnames()
    validate_generated_dashboards(data)
    print("Codestra Grafana observability control-plane validation: PASS")


if __name__ == "__main__":
    main()
