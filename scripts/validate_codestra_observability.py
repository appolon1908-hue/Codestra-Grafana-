#!/usr/bin/env python3
"""Fail-closed validation for the Codestra Grafana corporate overlay."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CODESTRA = ROOT / "codestra"
REGISTRY = CODESTRA / "business-registry.json"
INI = CODESTRA / "config" / "grafana.ini"
DATASOURCES = CODESTRA / "provisioning" / "datasources" / "codestra.yml"
DASHBOARD_PROVISIONING = CODESTRA / "provisioning" / "dashboards" / "codestra.yml"
RBAC = CODESTRA / "rbac-policy.json"
RUNTIME = CODESTRA / "runtime.v1.json"
COMPOSE = CODESTRA / "deploy" / "compose.candidate.yaml"
DOCKERFILE = CODESTRA / "deploy" / "Dockerfile"
DASHBOARDS = CODESTRA / "dashboards"
GENERATOR = ROOT / "scripts" / "generate_codestra_dashboards.py"

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
    "codestra",
    "moneybee",
    "beyvra",
    "breero",
    "larim-a",
    "transportation",
    "booked4seasons",
    "social",
    "klyrow",
    "telnexa",
    "kyqra",
    "restaurant",
    "provisioning",
}
REQUIRED_PLATFORM_SERVICES = {
    "caddy",
    "kong",
    "keycloak",
    "middleware",
    "odoo",
    "n8n",
    "vicidial",
    "prometheus",
    "loki",
    "tempo",
    "grafana",
    "opentelemetry-collector",
    "alloy",
    "node-exporter",
    "cadvisor",
    "redis-exporter",
    "blackbox-exporter",
    "superset",
    "openbao",
}
EXPECTED_DATASOURCES = {
    "codestra-prometheus": ("prometheus", "http://prometheus:9090"),
    "codestra-loki": ("loki", "http://loki-query:3100"),
    "codestra-tempo": ("tempo", "http://tempo:3200"),
    "codestra-alertmanager": ("alertmanager", "http://alertmanager:9093"),
}
EXPECTED_FOLDER_UIDS = {
    "codestra-executive",
    "codestra-incident",
    "codestra-platform",
    "codestra-business",
    "codestra-environment",
    "codestra-server",
    "codestra-database",
    "codestra-api",
    "codestra-security",
    "codestra-contact-center",
    "codestra-deployment",
    "codestra-slo",
}
EXPECTED_OAUTH_ROLES = {
    "observability-viewer": "Viewer",
    "observability-operator": "Editor",
    "observability-admin": "GrafanaAdmin",
}
FORBIDDEN_DASHBOARD_TOKENS = {
    "codestra_managed",
    "http_server_requests_total",
    "codestra_build_info",
    "tenant_id=",
    "tenant_id=~",
    "customer_id=",
    "customer_id=~",
    "account_id=",
    "account_id=~",
    "user_id=",
    "user_id=~",
}
REQUIRED_DASHBOARD_TOKENS = {
    "codestra:http_requests:rate5m",
    "codestra:http_error_ratio:5m",
    "codestra:http_duration_seconds:p95_5m",
    "codestra:slo_http_burn_rate:5m",
    "codestra:deployment_info:max",
    "ALERTS",
    "codestra_business",
    "environment",
    "region",
    "deployment",
    "service",
}
REQUIRED_TITLES = {
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
    "Environment Health",
    "Server and Container Health",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid YAML {path.relative_to(ROOT)}: {exc}")


def require_fragments(text: str, fragments: tuple[str, ...], source: str) -> None:
    for fragment in fragments:
        if fragment not in text:
            fail(f"{source} must contain: {fragment}")


def reject_fragments(text: str, fragments: tuple[str, ...], source: str) -> None:
    lowered = text.lower()
    for fragment in fragments:
        if fragment.lower() in lowered:
            fail(f"{source} contains forbidden content: {fragment}")


def validate_registry() -> dict[str, Any]:
    data = load_json(REGISTRY)
    if data.get("schema_version") != "2.0":
        fail("business registry schema_version must be 2.0")
    if data.get("status") != "REGISTRY_PREPARED_NOT_DEPLOYED":
        fail("business registry status must remain REGISTRY_PREPARED_NOT_DEPLOYED")

    businesses = data.get("businesses", [])
    business_ids = [business.get("id") for business in businesses]
    if set(business_ids) != REQUIRED_BUSINESSES:
        fail("business registry must exactly match the Codestra portfolio")
    if len(business_ids) != len(set(business_ids)):
        fail("duplicate business IDs")

    repos: list[str] = []
    services: list[str] = []
    teams: list[str] = []
    for business in businesses:
        if not business.get("display_name") or not business.get("service_tier"):
            fail(f"business metadata is incomplete: {business.get('id')}")
        teams.append(business.get("team", ""))
        repositories = business.get("repositories", [])
        if not repositories:
            fail(f"business {business['id']} has no registered application")
        for application in repositories:
            if application.get("profile") not in {"frontend", "backend", "fullstack"}:
                fail(f"invalid application profile for {application.get('repo')}")
            if not application.get("repo", "").startswith("appolon1908-hue/"):
                fail(f"unowned repository in registry: {application.get('repo')}")
            repos.append(application["repo"])
            services.append(application["service"])

    if len(repos) != len(set(repos)):
        fail("a runtime repository is assigned to more than one business")
    if len(services) != len(set(services)):
        fail("duplicate canonical application service names")
    if len(teams) != len(set(teams)) or any(not team for team in teams):
        fail("business team names must be unique and non-empty")

    platform_services = {
        item.get("service")
        for item in data.get("platform_services", [])
        if isinstance(item, dict)
    }
    missing = REQUIRED_PLATFORM_SERVICES - platform_services
    if missing:
        fail(f"missing platform services: {sorted(missing)}")

    telemetry_contract = data.get("telemetry_contract", {})
    required_dimensions = {
        "codestra_business",
        "application",
        "service",
        "environment",
        "server",
        "region",
        "deployment",
    }
    if set(telemetry_contract.get("required_labels", [])) != required_dimensions:
        fail("registry telemetry dimensions do not match the corporate contract")
    if telemetry_contract.get("customer_or_person_level_data") != "forbidden":
        fail("customer/person-level Grafana data must remain forbidden")
    return data


def validate_ini() -> None:
    ini = INI.read_text(encoding="utf-8")
    require_fragments(
        ini,
        (
            "app_mode = production",
            "domain = graf.codestra.media",
            "root_url = https://graf.codestra.media/",
            "enforce_domain = true",
            "type = postgres",
            "ssl_mode = verify-full",
            "user = $__file{/run/secrets/grafana_database_user}",
            "password = $__file{/run/secrets/grafana_database_password}",
            "ca_cert_path = /run/secrets/grafana_database_ca",
            "disable_login_form = true",
            "[auth.basic]\nenabled = false",
            "[auth.proxy]\nenabled = false",
            "client_id = grafana-observability",
            "client_secret = $__file{/run/secrets/grafana_oidc_client_secret}",
            "use_pkce = true",
            "use_refresh_token = true",
            "role_attribute_strict = true",
            "observability-admin",
            "observability-operator",
            "observability-viewer",
            "[auth.anonymous]\nenabled = false",
            "disable_initial_admin_creation = true",
            "secret_key = $__file{/run/secrets/grafana_secret_key}",
            "encryption_provider = secretKey.v1",
            "data_source_proxy_whitelist = prometheus:9090 loki-query:3100 tempo:3200 alertmanager:9093",
            "cookie_secure = true",
            "allow_embedding = false",
            "strict_transport_security = true",
            "content_security_policy = true",
            "[snapshots]\nenabled = false",
            "external_enabled = false",
            "[public_dashboards]\nenabled = false",
            "[unified_alerting]\nenabled = false",
            "[alerting]\nenabled = false",
            "[smtp]\nenabled = false",
            "reporting_enabled = false",
            "format = json",
        ),
        "codestra/config/grafana.ini",
    )
    reject_fragments(
        ini,
        (
            "admin_password = admin",
            "client_secret = changeme",
            "allow_embedding = true",
            "anonymous]\nenabled = true",
            "smtp]\nenabled = true",
        ),
        "codestra/config/grafana.ini",
    )


def validate_datasources() -> None:
    document = load_yaml(DATASOURCES)
    if document.get("apiVersion") != 1 or document.get("prune") is not True:
        fail("datasource provisioning must be apiVersion 1 with pruning enabled")
    sources = document.get("datasources", [])
    by_uid = {source.get("uid"): source for source in sources}
    if set(by_uid) != set(EXPECTED_DATASOURCES):
        fail("provisioned datasource UIDs do not match the corporate contract")

    for uid, (kind, url) in EXPECTED_DATASOURCES.items():
        source = by_uid[uid]
        if source.get("type") != kind or source.get("url") != url:
            fail(f"datasource {uid} does not use its private canonical endpoint")
        if source.get("access") != "proxy" or source.get("editable") is not False:
            fail(f"datasource {uid} must be server-proxy and immutable")
        if source.get("jsonData", {}).get("tlsSkipVerify") is not False:
            fail(f"datasource {uid} may not skip TLS verification policy")

    prometheus = by_uid["codestra-prometheus"]
    if prometheus.get("jsonData", {}).get("manageAlerts") is not False:
        fail("Grafana may not manage Prometheus alerts")
    if not prometheus.get("jsonData", {}).get("exemplarTraceIdDestinations"):
        fail("Prometheus exemplars must link to Tempo")

    loki = by_uid["codestra-loki"]
    if not loki.get("jsonData", {}).get("derivedFields"):
        fail("Loki must provide trace/correlation derived fields")

    tempo = by_uid["codestra-tempo"]
    tempo_json = tempo.get("jsonData", {})
    if not tempo_json.get("tracesToLogsV2") or not tempo_json.get("tracesToMetrics"):
        fail("Tempo log and metric correlation is incomplete")
    if tempo_json.get("serviceMap", {}).get("datasourceUid") != "codestra-prometheus":
        fail("Tempo service maps must use Codestra Prometheus")

    alertmanager = by_uid["codestra-alertmanager"]
    if alertmanager.get("jsonData", {}).get("handleGrafanaManagedAlerts") is not False:
        fail("Alertmanager datasource must remain read-only")

    serialized = DATASOURCES.read_text(encoding="utf-8")
    reject_fragments(
        serialized,
        (
            "https://prom.codestra.media",
            "https://loki.codestra.media",
            "https://temp.codestra.media",
            "https://aler.codestra.media",
            "basicAuthPassword",
            "secureJsonData",
        ),
        "datasource provisioning",
    )


def validate_dashboard_provisioning() -> None:
    document = load_yaml(DASHBOARD_PROVISIONING)
    providers = document.get("providers", [])
    folder_uids = {provider.get("folderUid") for provider in providers}
    if folder_uids != EXPECTED_FOLDER_UIDS:
        fail("dashboard folders do not match the corporate folder catalogue")
    for provider in providers:
        if provider.get("type") != "file":
            fail(f"dashboard provider must be file-based: {provider.get('name')}")
        if provider.get("disableDeletion") is not True:
            fail(f"dashboard deletion must be disabled: {provider.get('name')}")
        if provider.get("allowUiUpdates") is not False:
            fail(f"UI updates must be disabled: {provider.get('name')}")
        path = provider.get("options", {}).get("path", "")
        if not path.startswith("/etc/grafana/codestra-dashboards/"):
            fail(f"dashboard provider uses a non-immutable path: {provider.get('name')}")


def validate_rbac() -> None:
    policy = load_json(RBAC)
    if policy.get("schema_version") != "2.0":
        fail("RBAC schema_version must be 2.0")
    if policy.get("status") != "POLICY_PREPARED_NOT_APPLIED":
        fail("RBAC policy must remain prepared, not applied")
    if policy.get("default_org_role") != "Viewer":
        fail("normal users must default to Viewer")
    if policy.get("oauth_realm_roles") != EXPECTED_OAUTH_ROLES:
        fail("OAuth realm-role mapping is not the approved corporate mapping")

    privilege_rules = policy.get("privilege_rules", {})
    expected_false = {
        "anonymous_access",
        "local_login_form",
        "initial_local_admin",
        "viewer_can_edit",
        "grafana_managed_alerts",
    }
    for key in expected_false:
        if privilege_rules.get(key) is not False:
            fail(f"RBAC privilege must remain false: {key}")
    if privilege_rules.get("provisioned_dashboards_are_read_only") is not True:
        fail("provisioned dashboards must be read-only")

    teams = policy.get("teams", [])
    team_by_scope = {team.get("scope"): team for team in teams}
    for business in REQUIRED_BUSINESSES:
        team = team_by_scope.get(f"business:{business}")
        if not team or team.get("permission") != "View":
            fail(f"business team must exist with View permission: {business}")
    boundary = policy.get("data_access_boundary", {})
    if boundary.get("folder_permissions_are_not_datasource_isolation") is not True:
        fail("RBAC policy must reject folder-only isolation claims")
    if boundary.get("customer_or_person_level_data_forbidden") is not True:
        fail("RBAC policy must forbid customer/person-level data")


def validate_runtime() -> None:
    runtime = load_json(RUNTIME)
    if runtime.get("schemaVersion") != "2.0":
        fail("Grafana runtime schemaVersion must be 2.0")
    if runtime.get("status") != "CONFIG_PREPARED_NOT_DEPLOYED":
        fail("Grafana runtime must remain CONFIG_PREPARED_NOT_DEPLOYED")
    if runtime.get("hostname") != "graf.codestra.media":
        fail("Grafana runtime hostname mismatch")
    if runtime.get("hostBind") != "127.0.0.1:3000":
        fail("Grafana runtime must bind to loopback by default")
    if runtime.get("publicNativePortAllowed") is not False:
        fail("native Grafana port may not be public")
    if set(runtime.get("businessScope", [])) != REQUIRED_BUSINESSES:
        fail("Grafana runtime business scope is incomplete")
    if runtime.get("oidc", {}).get("roleMapping") != EXPECTED_OAUTH_ROLES:
        fail("runtime OIDC role mapping mismatch")
    if runtime.get("oidc", {}).get("clientSecretFile") != "/run/secrets/grafana_oidc_client_secret":
        fail("runtime OIDC secret must be file-injected")
    if any(value is not False for value in runtime.get("activation", {}).values()):
        fail("all Grafana activation gates must remain false before deployment evidence")
    boundaries = runtime.get("authorityBoundaries", {})
    for key in (
        "grafanaManagedAlerting",
        "businessMutation",
        "customerLevelDataAuthority",
        "tradingMutation",
        "communicationsDelivery",
        "folderPermissionsAloneClaimDatasourceIsolation",
    ):
        if boundaries.get(key) is not False:
            fail(f"authority boundary must remain false: {key}")


def validate_packaging() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    require_fragments(
        dockerfile,
        (
            "ARG PYTHON_BUILDER_IMAGE",
            "ARG GRAFANA_IMAGE",
            "# syntax=docker.io/docker/dockerfile@sha256:",
            "AS dashboard-builder",
            "python3 scripts/generate_codestra_dashboards.py",
            "find codestra/dashboards",
            "FROM ${GRAFANA_IMAGE}",
            "/etc/grafana/grafana.ini",
            "/etc/grafana/provisioning/",
            "/etc/grafana/codestra-dashboards/",
            "/usr/share/codestra/runtime-base.lock.json",
            "USER 472:0",
        ),
        "codestra/deploy/Dockerfile",
    )
    reject_fragments(
        dockerfile,
        ("COPY .env", "COPY *secret*", "latest AS", "curl | sh", "wget | sh"),
        "codestra/deploy/Dockerfile",
    )

    compose = load_yaml(COMPOSE)
    service = compose.get("services", {}).get("grafana")
    if not service:
        fail("Compose candidate must define the Grafana service")
    if service.get("read_only") is not True or service.get("user") != "472:0":
        fail("Grafana must run non-root with a read-only root filesystem")
    if service.get("privileged") is True or service.get("network_mode") == "host":
        fail("Grafana may not use privileged or host-network mode")
    if "ALL" not in service.get("cap_drop", []):
        fail("Grafana must drop all Linux capabilities")
    if "no-new-privileges:true" not in service.get("security_opt", []):
        fail("Grafana must set no-new-privileges")
    if not service.get("healthcheck"):
        fail("Grafana runtime requires a health check")
    if not service.get("volumes") or not any(
        str(volume).endswith(":/var/lib/grafana") for volume in service.get("volumes", [])
    ):
        fail("Grafana data must use a durable volume")

    ports = [str(port) for port in service.get("ports", [])]
    if ports != ["127.0.0.1:${GRAFANA_HOST_PORT:-3000}:3000"]:
        fail("Grafana must publish exactly one loopback-bound port")
    if set(service.get("networks", [])) != {"codestra-observability", "codestra-database"}:
        fail("Grafana must attach only to observability and database networks")
    expected_secrets = {
        "grafana_oidc_client_secret",
        "grafana_database_user",
        "grafana_database_password",
        "grafana_database_ca",
        "grafana_secret_key",
    }
    if set(service.get("secrets", [])) != expected_secrets:
        fail("Grafana runtime secret set is incomplete")

    image = str(service.get("image", ""))
    if "${CODESTRA_GRAFANA_IMAGE:" not in image or "sha256" not in image:
        fail("Grafana runtime image must require an immutable digest")
    if "build" in service:
        fail("Grafana deployment Compose must be deploy-only")
    environment = service.get("environment", {})
    if environment.get("CODESTRA_SOURCE_SHA") != "${CODESTRA_SOURCE_SHA:?exact protected source SHA is required}":
        fail("Grafana runtime source readback is missing")
    if environment.get("CODESTRA_IMAGE_DIGEST") != "${CODESTRA_IMAGE_DIGEST:?exact sha256 image digest is required}":
        fail("Grafana runtime image readback is missing")
    secret_definitions = compose.get("secrets", {})
    if set(secret_definitions) != expected_secrets:
        fail("Grafana top-level secret-file set is incomplete")
    if any(set(value) != {"file"} or not str(value["file"]).startswith("${GRAFANA_") for value in secret_definitions.values()):
        fail("Grafana credentials must be supplied only as mounted files")
    limits = service.get("deploy", {}).get("resources", {}).get("limits", {})
    for key in ("cpus", "memory", "pids"):
        if key not in limits:
            fail(f"Grafana runtime is missing resource limit: {key}")

    serialized = COMPOSE.read_text(encoding="utf-8")
    reject_fragments(
        serialized,
        ("/var/run/docker.sock", "0.0.0.0:3000", ":latest", "privileged: true"),
        "codestra/deploy/compose.candidate.yaml",
    )


def validate_hostnames() -> None:
    pattern = re.compile(
        r"(?<![A-Za-z0-9.-])([a-z0-9-]+\.codestra\.media)(?![A-Za-z0-9.-])"
    )
    for root in (CODESTRA, ROOT / "scripts"):
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".woff",
                ".woff2",
            }:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for host in pattern.findall(text):
                if host not in ALLOWED_MEDIA_HOSTS:
                    fail(
                        "alternate/unassigned codestra.media hostname "
                        f"{host} in {path.relative_to(ROOT)}"
                    )


def validate_generated_dashboards(data: dict[str, Any]) -> None:
    subprocess.run([sys.executable, str(GENERATOR)], check=True)
    files = sorted(DASHBOARDS.rglob("*.json"))
    expected = (
        2
        + 15
        + len(data["businesses"])
        + sum(len(business["repositories"]) for business in data["businesses"])
    )
    if len(files) != expected:
        fail(f"generated {len(files)} dashboards; expected exactly {expected}")

    uids: set[str] = set()
    titles: set[str] = set()
    all_serialized: list[str] = []
    business_dashboards: set[str] = set()
    for path in files:
        dashboard = load_json(path)
        uid = dashboard.get("uid")
        title = dashboard.get("title")
        if not uid or uid in uids:
            fail(f"missing or duplicate dashboard UID: {path.relative_to(ROOT)}")
        if not title or title in titles:
            fail(f"missing or duplicate dashboard title: {path.relative_to(ROOT)}")
        uids.add(uid)
        titles.add(title)
        if dashboard.get("editable") is not False:
            fail(f"provisioned dashboard must be read-only: {path.relative_to(ROOT)}")
        if dashboard.get("schemaVersion", 0) < 39:
            fail(f"dashboard schema is outdated: {path.relative_to(ROOT)}")
        if dashboard.get("links") not in ([], None):
            fail(f"source dashboards may not contain external/action links: {path.relative_to(ROOT)}")
        if not dashboard.get("panels"):
            fail(f"dashboard has no panels: {path.relative_to(ROOT)}")
        if any(panel.get("type") in {"button", "actions", "form-panel"} for panel in dashboard["panels"]):
            fail(f"dashboard contains a mutation-capable panel: {path.relative_to(ROOT)}")

        serialized = json.dumps(dashboard, sort_keys=True)
        all_serialized.append(serialized)
        lowered = serialized.lower()
        for token in FORBIDDEN_DASHBOARD_TOKENS:
            if token.lower() in lowered:
                fail(f"dashboard contains forbidden query token {token}: {path.relative_to(ROOT)}")
        if "business health" in title.lower():
            business_dashboards.add(uid.removeprefix("biz-"))

    if not REQUIRED_TITLES.issubset(titles):
        fail(f"missing required dashboards: {sorted(REQUIRED_TITLES - titles)}")
    if business_dashboards != {re.sub(r"[^a-z0-9-]+", "-", item).strip("-") for item in REQUIRED_BUSINESSES}:
        fail("each managed business must have exactly one business-health dashboard")

    portfolio = "\n".join(all_serialized)
    missing_tokens = [token for token in REQUIRED_DASHBOARD_TOKENS if token not in portfolio]
    if missing_tokens:
        fail(f"generated dashboards omit corporate telemetry tokens: {sorted(missing_tokens)}")
    if "Codestra" not in portfolio or "corporate" not in portfolio:
        fail("dashboard portfolio does not visibly represent Codestra corporate ownership")


def validate_secret_safety() -> None:
    marker = "-" * 5
    signatures = (
        marker + "BEGIN " + "PRIVATE KEY" + marker,
        marker + "BEGIN " + "OPENSSH PRIVATE KEY" + marker,
        "AK" + "IA",
    )
    for root in (CODESTRA, ROOT / "scripts"):
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for signature in signatures:
                if signature in text:
                    fail(f"secret-shaped material in {path.relative_to(ROOT)}")

    ini = INI.read_text(encoding="utf-8")
    for match in re.finditer(r"(?im)^client_secret\s*=\s*(.+)$", ini):
        if not match.group(1).strip().startswith("$__file{"):
            fail("Grafana OAuth client secret is populated in source")
    for match in re.finditer(r"(?im)^secret_key\s*=\s*(.+)$", ini):
        if not match.group(1).strip().startswith("$__file{"):
            fail("Grafana state secret key is populated in source")


def main() -> None:
    data = validate_registry()
    validate_ini()
    validate_datasources()
    validate_dashboard_provisioning()
    validate_rbac()
    validate_runtime()
    validate_packaging()
    validate_hostnames()
    validate_generated_dashboards(data)
    validate_secret_safety()
    print("Codestra Grafana corporate observability validation: PASS")


if __name__ == "__main__":
    main()
