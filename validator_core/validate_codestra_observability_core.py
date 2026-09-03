from __future__ import annotations

import hashlib
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
INI = CODESTRA / "grafana.ini"
DATASOURCE_DIR = CODESTRA / "provisioning" / "datasources"
DASHBOARD_PROVISIONING = CODESTRA / "provisioning" / "dashboards" / "dashboards.yml"
DASHBOARDS = CODESTRA / "dashboards"
RBAC = CODESTRA / "rbac-policy.json"
RUNTIME = CODESTRA / "runtime.v1.json"
COMPOSE = CODESTRA / "deploy" / "compose.candidate.yaml"
DOCKERFILE = CODESTRA / "deploy" / "Dockerfile"
ENTRYPOINT = CODESTRA / "deploy" / "entrypoint.sh"
GENERATOR = ROOT / "scripts" / "generate_codestra_dashboards.py"

ALLOWED_MEDIA_HOSTS = {
    "graf.codestra.media",
    "supe.codestra.media",
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
REQUIRED_TITLES = {
    "Codestra Platform Command Center",
    "Codestra API Operations",
}
REQUIRED_DASHBOARD_TOKENS = {
    "codestra_http_requests_total",
    "codestra_http_request_duration_seconds",
    "codestra_outbox_backlog",
    "codestra_inbox_backlog",
    "codestra_authentication_failures_total",
    "codestra_authorization_denials_total",
    "codestra_reconciliation_failures_total",
    "codestra_external_provider_failures_total",
    "codestra_deployment_info",
    "codestra_capability_state",
}
FORBIDDEN_DASHBOARD_TOKENS = {
    "tenant_id",
    "customer_id",
    "account_id",
    "user_id",
    "request_id",
    "correlation_id",
    "trace_id",
    "span_id",
    "email",
    "phone",
    "message_id",
    "order_id",
    "workflow_id",
    "execution_id",
    "raw_url",
    "query_string",
    "db_statement",
    "container_id",
    "pod_uid",
    "exception_message",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")
    if not isinstance(value, dict):
        fail(f"JSON root must be an object: {path.relative_to(ROOT)}")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid YAML {path.relative_to(ROOT)}: {exc}")
    if not isinstance(value, dict):
        fail(f"YAML root must be an object: {path.relative_to(ROOT)}")
    return value


def reject_fragments(text: str, fragments: tuple[str, ...], source: str) -> None:
    lowered = text.lower()
    for fragment in fragments:
        if fragment.lower() in lowered:
            fail(f"forbidden fragment {fragment!r} in {source}")


def validate_registry() -> dict[str, Any]:
    registry = load_json(REGISTRY)
    if registry.get("version") != 2:
        fail("business registry version must be 2")
    if registry.get("owner") != "Codestra Platform":
        fail("business registry owner is incorrect")
    if registry.get("status") != "CONFIG_PREPARED_NOT_DEPLOYED":
        fail("business registry must remain source-only")

    businesses = registry.get("businesses")
    if not isinstance(businesses, list):
        fail("business registry businesses must be a list")
    ids = {item.get("id") for item in businesses if isinstance(item, dict)}
    if ids != REQUIRED_BUSINESSES:
        fail(f"business registry IDs differ from authority: {sorted(ids)}")

    repositories: set[str] = set()
    for business in businesses:
        if not isinstance(business, dict):
            fail("business registry contains a non-object business")
        if business.get("service_tier") not in {"tier_1", "tier_2"}:
            fail(f"business has invalid service tier: {business.get('id')}")
        items = business.get("repositories")
        if not isinstance(items, list) or not items:
            fail(f"business has no repository inventory: {business.get('id')}")
        for item in items:
            if not isinstance(item, dict):
                fail("business registry contains a non-object repository")
            repository = item.get("repo")
            if not isinstance(repository, str) or not repository.startswith(
                "appolon1908-hue/"
            ):
                fail(f"repository leaves approved owner: {repository}")
            if repository in repositories:
                fail(f"repository appears more than once: {repository}")
            repositories.add(repository)
            for field in ("application", "service", "authority"):
                if not item.get(field):
                    fail(f"repository {repository} is missing {field}")

    platform_services = registry.get("platform_services")
    if not isinstance(platform_services, list) or not platform_services:
        fail("platform service authority is missing")
    return registry


def validate_ini() -> None:
    ini = INI.read_text(encoding="utf-8")
    required = (
        "[auth.generic_oauth]",
        "enabled = true",
        "allow_sign_up = false",
        "use_pkce = true",
        "auth_url = https://auth.codestra.co/realms/codestra/protocol/openid-connect/auth",
        "token_url = https://auth.codestra.co/realms/codestra/protocol/openid-connect/token",
        "api_url = https://auth.codestra.co/realms/codestra/protocol/openid-connect/userinfo",
        "signout_redirect_url = https://auth.codestra.co/realms/codestra/protocol/openid-connect/logout",
        "[auth.anonymous]",
        "enabled = false",
        "[users]",
        "allow_sign_up = false",
        "[security]",
        "cookie_secure = true",
        "cookie_samesite = strict",
        "strict_transport_security = true",
        "strict_transport_security_preload = true",
        "content_security_policy = true",
        "[database]",
        "type = postgres",
        "ssl_mode = verify-full",
        "[feature_toggles]",
        "enable = accessControlOnCall",
    )
    for fragment in required:
        if fragment not in ini:
            fail(f"grafana.ini is missing required setting: {fragment}")
    reject_fragments(
        ini,
        (
            "enabled = true\norg_role = Admin",
            "skip_org_role_sync = true",
            "tls_skip_verify_insecure = true",
            "allow_embedding = true",
        ),
        "codestra/grafana.ini",
    )


def validate_datasources() -> None:
    files = sorted(DATASOURCE_DIR.glob("*.yml")) + sorted(
        DATASOURCE_DIR.glob("*.yaml")
    )
    if not files:
        fail("Grafana datasource provisioning is missing")
    for path in files:
        document = load_yaml(path)
        for datasource in document.get("datasources", []):
            if not isinstance(datasource, dict):
                fail(f"invalid datasource in {path.relative_to(ROOT)}")
            if datasource.get("editable") is not False:
                fail(f"datasource must be source-fixed: {path.relative_to(ROOT)}")
            if datasource.get("access") != "proxy":
                fail(f"datasource must be server-side proxy: {path.relative_to(ROOT)}")
            url = str(datasource.get("url", ""))
            if not url or "localhost" in url or "127.0.0.1" in url:
                fail(f"datasource URL is not a private service identity: {url}")
            serialized = json.dumps(datasource).lower()
            reject_fragments(
                serialized,
                (
                    "basic_auth_password",
                    '"password"',
                    '"token"',
                    "client_secret",
                ),
                str(path.relative_to(ROOT)),
            )


def validate_dashboard_provisioning() -> None:
    document = load_yaml(DASHBOARD_PROVISIONING)
    providers = document.get("providers")
    if not isinstance(providers, list) or len(providers) != 1:
        fail("Grafana must have one dashboard provisioning provider")
    provider = providers[0]
    if provider.get("disableDeletion") is not True:
        fail("dashboard deletion must be disabled")
    if provider.get("allowUiUpdates") is not False:
        fail("dashboard UI updates must be disabled")
    if provider.get("updateIntervalSeconds", 0) < 30:
        fail("dashboard provisioning interval is too aggressive")
    if provider.get("options", {}).get("path") != "/etc/grafana/provisioning/dashboards/json":
        fail("dashboard provisioning path is incorrect")


def validate_rbac() -> None:
    rbac = load_json(RBAC)
    if rbac.get("status") != "POLICY_PREPARED_NOT_APPLIED":
        fail("Grafana RBAC policy must remain source-only")
    if rbac.get("default_role") != "Viewer":
        fail("Grafana default role must remain Viewer")
    roles = rbac.get("roles")
    if not isinstance(roles, dict):
        fail("Grafana RBAC roles are missing")
    if set(roles) != {"codestra-viewer", "codestra-editor", "codestra-admin"}:
        fail("Grafana RBAC role inventory is incorrect")
    if "admin" in roles["codestra-viewer"].get("permissions", []):
        fail("viewer role may not have admin permission")
    if rbac.get("business_access_enabled") is not False:
        fail("cross-business Grafana access must remain disabled")


def validate_runtime() -> None:
    runtime = load_json(RUNTIME)
    if runtime.get("status") != "CONFIG_PREPARED_NOT_DEPLOYED":
        fail("Grafana runtime must remain source-only")
    activation = runtime.get("activation")
    if not isinstance(activation, dict) or not activation:
        fail("Grafana runtime activation map is missing")
    if any(value is not False for value in activation.values()):
        fail("Grafana runtime activation flags must remain false")
    if runtime.get("public_hostname") != "graf.codestra.media":
        fail("Grafana public hostname authority is incorrect")
    if runtime.get("oidc_issuer") != "https://auth.codestra.co/realms/codestra":
        fail("Grafana OIDC issuer is incorrect")


def validate_packaging() -> None:
    compose = load_yaml(COMPOSE)
    services = compose.get("services")
    if not isinstance(services, dict) or set(services) != {"grafana"}:
        fail("Grafana candidate Compose must contain only the grafana service")
    service = services["grafana"]
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
    build_args = service.get("build", {}).get("args", {})
    if set(build_args) != {"PYTHON_BUILDER_IMAGE", "GRAFANA_IMAGE"}:
        fail("Grafana build must pin both builder and upstream base images")
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
        + 16
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
    # Generation is part of the validation process. Re-scan the materialized
    # dashboards so a generator cannot construct an unapproved hostname from
    # source fragments after the pre-generation scan has already passed.
    validate_hostnames()
    validate_secret_safety()
    print("Codestra Grafana corporate observability validation: PASS")


if __name__ == "__main__":
    main()
