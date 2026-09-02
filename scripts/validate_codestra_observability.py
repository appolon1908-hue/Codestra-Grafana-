#!/usr/bin/env python3
"""Governed entry point for the Codestra Grafana corporate validator.

The full pre-existing validator is preserved as an exact core blob. This entry
point removes the retired public PostgreSQL Exporter hostname before compiling
that core, then adds fail-closed checks for the private service authority and
repository-name migration aliases.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "validator_core" / "validate_codestra_observability_core.py"
POSTGRES_POLICY = ROOT / "governance" / "private-service-authority.v1.json"
REPOSITORY_ALIASES = ROOT / "governance" / "repository-name-aliases.v1.json"
BUSINESS_REGISTRY = ROOT / "codestra" / "business-registry.json"
FORBIDDEN_POSTGRES_HOST = "pgex" + ".codestra.media"
PRIVATE_POSTGRES_IDENTITY = "postgres-exporter:9187"
REQUIRED_REPOSITORY_ALIASES = {
    1221155447: (
        "appolon1908-hue/Frontend-Resturant-",
        "appolon1908-hue/restaurant-frontend",
    ),
    1343761049: (
        "appolon1908-hue/transportaion-Frontend",
        "appolon1908-hue/freight-platform-frontend",
    ),
    1343962199: (
        "appolon1908-hue/LARIM-A-Fornt-end",
        "appolon1908-hue/LARIM-A-Frontend",
    ),
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def load_core() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "codestra_observability_validator_core",
        CORE,
    )
    if spec is None or spec.loader is None:
        fail("validator core cannot be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


def contains_forbidden_postgres_hostname(text: str) -> bool:
    return FORBIDDEN_POSTGRES_HOST in text.lower()


def is_ignored_source_path(path: Path) -> bool:
    ignored_suffixes = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".woff",
        ".woff2",
        ".zip",
        ".gz",
        ".pyc",
    }
    return (
        path.suffix.lower() in ignored_suffixes
        or ".git" in path.parts
        or "__pycache__" in path.parts
    )


def validate_postgres_exporter_document(document: Any) -> None:
    if document.get("schema_version") != "1.0":
        fail("private service authority schema_version must be 1.0")
    if document.get("status") != "ACTIVE_SOURCE_AUTHORITY":
        fail("private service authority must be active")

    service = document.get("postgres_exporter", {})
    if service.get("repository_id") != 1350839865:
        fail("PostgreSQL Exporter repository identity is not stable")
    if service.get("repository") != "appolon1908-hue/Codestra-Postgres-Exporter":
        fail("PostgreSQL Exporter principal repository is incorrect")
    if service.get("public_hostname") is not None:
        fail("PostgreSQL Exporter may not have a public hostname")
    if service.get("private_service_identity") != PRIVATE_POSTGRES_IDENTITY:
        fail("PostgreSQL Exporter private service identity is incorrect")
    if service.get("forbidden_public_hostname") != FORBIDDEN_POSTGRES_HOST:
        fail("retired PostgreSQL Exporter public hostname is not explicitly forbidden")
    if service.get("exposure") != "PRIVATE_INTERNAL_ONLY":
        fail("PostgreSQL Exporter exposure must remain private/internal only")
    for field in ("caddy_publication_allowed", "kong_publication_allowed"):
        if service.get(field) is not False:
            fail(f"PostgreSQL Exporter {field} must remain false")


def validate_postgres_exporter_authority() -> None:
    document = load_json(POSTGRES_POLICY)
    validate_postgres_exporter_document(document)

    allowed_literal_locations = {POSTGRES_POLICY.resolve()}
    for path in ROOT.rglob("*"):
        if not path.is_file() or is_ignored_source_path(path):
            continue
        if path.resolve() in allowed_literal_locations:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if contains_forbidden_postgres_hostname(text):
            fail(
                "retired PostgreSQL Exporter public hostname remains in active source: "
                f"{path.relative_to(ROOT)}"
            )


def registry_repositories(registry_text: str) -> set[str]:
    try:
        registry = json.loads(registry_text)
    except json.JSONDecodeError:
        fail("business registry is not valid JSON")

    repositories: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            repository = value.get("repo")
            if isinstance(repository, str):
                repositories.add(repository)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(registry)
    return repositories


def validate_repository_alias_document(document: Any, registry_text: str) -> None:
    if document.get("schema_version") != "1.0":
        fail("repository alias schema_version must be 1.0")
    if document.get("status") != "PREPARED_NOT_RENAMED":
        fail("Grafana repository aliases must remain prepared until GitHub cutover")

    mappings = document.get("mappings", [])
    if not mappings:
        fail("repository alias mappings are empty")
    registered_repositories = registry_repositories(registry_text)

    repository_ids: set[int] = set()
    current_names: set[str] = set()
    target_names: set[str] = set()
    for mapping in mappings:
        repository_id = mapping.get("repository_id")
        current = mapping.get("current_repository", "")
        target = mapping.get("target_repository_after_cutover", "")
        state = mapping.get("status")

        if not isinstance(repository_id, int) or repository_id <= 0:
            fail("repository alias contains an invalid stable ID")
        if repository_id in repository_ids:
            fail(f"duplicate repository alias ID: {repository_id}")
        if current in current_names or target in target_names:
            fail("repository alias contains duplicate current or target names")
        if not current.startswith("appolon1908-hue/") or not target.startswith(
            "appolon1908-hue/"
        ):
            fail("repository alias leaves the approved owner")
        if state != "PREPARED_NOT_RENAMED":
            fail(f"repository alias changed state without cutover: {current}")
        if current not in registered_repositories:
            fail(f"business registry lost the current operational repository: {current}")
        if target in registered_repositories:
            fail(f"business registry uses a target repository before cutover: {target}")

        repository_ids.add(repository_id)
        current_names.add(current)
        target_names.add(target)

    expected_ids = set(REQUIRED_REPOSITORY_ALIASES)
    if repository_ids != expected_ids:
        missing = sorted(expected_ids - repository_ids)
        unexpected = sorted(repository_ids - expected_ids)
        fail(
            "repository alias set differs from governed authority "
            f"(missing={missing}, unexpected={unexpected})"
        )

    for mapping in mappings:
        expected = REQUIRED_REPOSITORY_ALIASES[mapping["repository_id"]]
        actual = (
            mapping.get("current_repository"),
            mapping.get("target_repository_after_cutover"),
        )
        if actual != expected:
            fail(
                "repository alias identity changed for stable ID "
                f"{mapping['repository_id']}"
            )


def validate_repository_aliases() -> None:
    document = load_json(REPOSITORY_ALIASES)
    registry_text = BUSINESS_REGISTRY.read_text(encoding="utf-8")
    validate_repository_alias_document(document, registry_text)


def main() -> None:
    core = load_core()
    original_validate_hostnames = core.validate_hostnames

    def governed_validate_hostnames() -> None:
        original_validate_hostnames()
        validate_postgres_exporter_authority()
        validate_repository_aliases()

    core.validate_hostnames = governed_validate_hostnames
    core.main()


if __name__ == "__main__":
    main()
