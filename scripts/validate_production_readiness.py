#!/usr/bin/env python3
"""Validate the fail-closed Codestra Grafana production-source contract."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "production-readiness" / "production-readiness.v1.json"
GUIDE = ROOT / "production-readiness" / "PRODUCTION_READINESS.md"
RUNTIME = ROOT / "codestra" / "runtime.v1.json"
COMPOSE = ROOT / "codestra" / "deploy" / "compose.candidate.yaml"
GRAFANA_INI = ROOT / "codestra" / "grafana.ini"
PRIVATE_AUTHORITY = ROOT / "governance" / "private-service-authority.v1.json"

EXPECTED_REPOSITORY = "appolon1908-hue/Codestra-Grafana-"
EXPECTED_REPOSITORY_ID = 1350767762
EXPECTED_SERVER = "37.27.128.39"
EXPECTED_PUBLIC_HOST = "graf.codestra.media"
EXPECTED_ISSUER = "https://auth.codestra.co/realms/codestra"
PRIVATE_EXPORTER = "postgres-exporter:9187"
RETIRED_EXPORTER_HOST = "pgex" + ".codestra.media"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        fail(f"required JSON file is missing: {path.relative_to(ROOT)}")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
        )
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")
    if not isinstance(value, dict):
        fail(f"JSON root must be an object: {path.relative_to(ROOT)}")
    return value


def require_exact(document: dict[str, Any], expected: dict[str, Any], source: str) -> None:
    for key, value in expected.items():
        if document.get(key) != value:
            fail(f"{source} field {key!r} is incorrect")


def validate_manifest() -> dict[str, Any]:
    document = load_json(MANIFEST)
    require_exact(
        document,
        {
            "schema_version": "1.0",
            "repository_id": EXPECTED_REPOSITORY_ID,
            "repository": EXPECTED_REPOSITORY,
            "component": "grafana",
            "authority": "CODESTRA_GRAFANA_PRODUCTION_SOURCE",
            "target_server": EXPECTED_SERVER,
            "public_hostname": EXPECTED_PUBLIC_HOST,
            "oidc_issuer": EXPECTED_ISSUER,
            "source_state": "PRODUCTION_SOURCE_CANDIDATE",
            "runtime_state": "NOT_CERTIFIED_NOT_DEPLOYED_BY_THIS_CHANGE",
        },
        "production readiness manifest",
    )

    if document.get("private_dependencies") != ["prometheus", "postgresql"]:
        fail("Grafana private dependency inventory is incorrect")

    exporter = document.get("private_postgresql_exporter")
    if not isinstance(exporter, dict):
        fail("private PostgreSQL Exporter contract is missing")
    require_exact(
        exporter,
        {
            "service_identity": PRIVATE_EXPORTER,
            "public_hostname": None,
            "public_route_allowed": False,
            "host_public_port_allowed": False,
        },
        "private PostgreSQL Exporter contract",
    )

    release_policy = document.get("release_policy")
    if not isinstance(release_policy, dict) or not release_policy:
        fail("release policy is missing")
    for key in (
        "protected_source_sha_required",
        "immutable_image_digest_required",
        "floating_image_tags_forbidden",
        "sbom_required",
        "provenance_required",
        "signature_verification_required",
        "isolated_staging_required",
        "rollback_digest_required",
        "configuration_checksum_required",
        "post_deploy_runtime_readback_required",
        "production_environment_approval_required",
    ):
        if release_policy.get(key) is not True:
            fail(f"required release policy is not true: {key}")

    runtime_safety = document.get("runtime_safety")
    if not isinstance(runtime_safety, dict):
        fail("runtime safety policy is missing")
    for key in (
        "anonymous_admin_allowed",
        "browser_datasource_credentials_allowed",
        "docker_socket_allowed",
        "host_network_allowed",
        "privileged_container_allowed",
        "runtime_activation_authorized_by_source_merge",
        "workload_restart_authorized_by_source_merge",
    ):
        if runtime_safety.get(key) is not False:
            fail(f"runtime safety field must remain false: {key}")

    required_files = document.get("required_source_files")
    if not isinstance(required_files, list) or not required_files:
        fail("required source file inventory is missing")
    if len(required_files) != len(set(required_files)):
        fail("required source file inventory contains duplicates")
    for relative in required_files:
        if not isinstance(relative, str) or not relative:
            fail("required source file entry is invalid")
        if not (ROOT / relative).exists():
            fail(f"required production source is missing: {relative}")

    for key in ("required_source_checks", "production_exit_criteria"):
        values = document.get(key)
        if not isinstance(values, list) or len(values) < 5:
            fail(f"{key} is incomplete")
        if not all(isinstance(item, str) and item for item in values):
            fail(f"{key} contains an invalid entry")

    return document


def validate_runtime_source() -> None:
    runtime = load_json(RUNTIME)
    require_exact(
        runtime,
        {
            "status": "CONFIG_PREPARED_NOT_DEPLOYED",
            "public_hostname": EXPECTED_PUBLIC_HOST,
            "oidc_issuer": EXPECTED_ISSUER,
        },
        "Grafana runtime authority",
    )
    activation = runtime.get("activation")
    if not isinstance(activation, dict) or not activation:
        fail("Grafana runtime activation map is missing")
    if any(value is not False for value in activation.values()):
        fail("source readiness may not activate Grafana runtime capabilities")


def validate_private_authority() -> None:
    document = load_json(PRIVATE_AUTHORITY)
    service = document.get("postgres_exporter")
    if not isinstance(service, dict):
        fail("PostgreSQL Exporter authority is missing")
    require_exact(
        service,
        {
            "repository_id": 1350839865,
            "repository": "appolon1908-hue/Codestra-Postgres-Exporter",
            "public_hostname": None,
            "private_service_identity": PRIVATE_EXPORTER,
            "forbidden_public_hostname": RETIRED_EXPORTER_HOST,
            "exposure": "PRIVATE_INTERNAL_ONLY",
            "caddy_publication_allowed": False,
            "kong_publication_allowed": False,
        },
        "PostgreSQL Exporter authority",
    )


def validate_grafana_configuration() -> None:
    ini = GRAFANA_INI.read_text(encoding="utf-8")
    for required in (
        "[auth.generic_oauth]",
        "allow_sign_up = false",
        "use_pkce = true",
        "[auth.anonymous]",
        "enabled = false",
        "cookie_secure = true",
        "cookie_samesite = strict",
        "strict_transport_security = true",
        "content_security_policy = true",
        "ssl_mode = verify-full",
    ):
        if required not in ini:
            fail(f"grafana.ini is missing production control: {required}")
    if EXPECTED_ISSUER not in ini:
        fail("grafana.ini does not use the canonical Codestra issuer")


def validate_candidate_compose() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    lowered = text.lower()
    forbidden = (
        ":latest",
        "privileged: true",
        "network_mode: host",
        "/var/run/docker.sock",
        "0.0.0.0:3000",
        "::0:3000",
    )
    for fragment in forbidden:
        if fragment in lowered:
            fail(f"candidate Compose contains forbidden fragment: {fragment}")
    if "sha256" not in lowered:
        fail("candidate Compose does not require an immutable image digest")
    if "127.0.0.1:${grafana_host_port:-3000}:3000" not in lowered:
        fail("Grafana candidate port is not loopback-bound")
    for required in (
        "healthcheck:",
        "cap_drop:",
        "no-new-privileges:true",
        "read_only:",
        "codestra-observability",
        "codestra-database",
    ):
        if required not in lowered:
            fail(f"candidate Compose is missing production hardening: {required}")


def validate_guide() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    for required in (
        "SOURCE_STATE=PRODUCTION_SOURCE_CANDIDATE",
        "RUNTIME_STATE=NOT_CERTIFIED_NOT_DEPLOYED_BY_THIS_CHANGE",
        "IMAGE=ghcr.io/appolon1908-hue/<approved-image>@sha256:<digest>",
        "SIGNATURE_VERIFICATION=PASS",
        "TARGET_SERVER=37.27.128.39",
        "IMAGE_DIGEST_MATCH=PASS",
        "PUBLIC_POSTGRES_EXPORTER_ROUTE=ABSENT",
        "SOURCE_READY_RUNTIME_NOT_CERTIFIED",
    ):
        if required not in text:
            fail(f"production readiness guide is missing evidence field: {required}")


def validate_repository_scan() -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".woff", ".woff2", ".pyc"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if RETIRED_EXPORTER_HOST in text.lower() and path.resolve() != PRIVATE_AUTHORITY.resolve():
            fail(f"retired exporter hostname remains outside its denial authority: {path.relative_to(ROOT)}")
        if re.search(r"(?im)^\s*image\s*:\s*[^#\n]*:latest\s*$", text):
            fail(f"floating latest image is forbidden: {path.relative_to(ROOT)}")


def main() -> None:
    validate_manifest()
    validate_runtime_source()
    validate_private_authority()
    validate_grafana_configuration()
    validate_candidate_compose()
    validate_guide()
    validate_repository_scan()
    print("Codestra Grafana production source readiness: PASS")


if __name__ == "__main__":
    main()
