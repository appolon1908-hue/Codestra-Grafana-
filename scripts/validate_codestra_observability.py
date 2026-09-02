#!/usr/bin/env python3
"""Governed entry point for the Codestra Grafana corporate validator.

The full pre-existing validator is preserved as an exact core blob. This entry
point removes the retired public PostgreSQL Exporter hostname before compiling
that core, then adds fail-closed checks for the private service authority and
repository-name migration aliases.
"""

from __future__ import annotations

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


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def load_core() -> ModuleType:
    source = CORE.read_text(encoding="utf-8")
    retired_entry = f'    "{FORBIDDEN_POSTGRES_HOST}",\n'
    if source.count(retired_entry) != 1:
        fail("validator core does not contain the single expected retired-host entry")
    source = source.replace(retired_entry, "", 1)

    module = ModuleType("codestra_observability_validator_core")
    module.__file__ = str(CORE)
    sys.modules[module.__name__] = module
    exec(compile(source, str(CORE), "exec"), module.__dict__)
    return module


def validate_postgres_exporter_authority() -> None:
    document = load_json(POSTGRES_POLICY)
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

    allowed_literal_locations = {CORE.resolve(), POSTGRES_POLICY.resolve()}
    ignored_suffixes = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".woff",
        ".woff2",
        ".zip",
        ".gz",
    }
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() in ignored_suffixes:
            continue
        if path.resolve() in allowed_literal_locations:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if FORBIDDEN_POSTGRES_HOST in text:
            fail(
                "retired PostgreSQL Exporter public hostname remains in active source: "
                f"{path.relative_to(ROOT)}"
            )


def validate_repository_aliases() -> None:
    document = load_json(REPOSITORY_ALIASES)
    if document.get("schema_version") != "1.0":
        fail("repository alias schema_version must be 1.0")
    if document.get("status") != "PREPARED_NOT_RENAMED":
        fail("Grafana repository aliases must remain prepared until GitHub cutover")

    mappings = document.get("mappings", [])
    if not mappings:
        fail("repository alias mappings are empty")

    repository_ids: set[int] = set()
    current_names: set[str] = set()
    target_names: set[str] = set()
    registry_text = BUSINESS_REGISTRY.read_text(encoding="utf-8")

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
        if current not in registry_text:
            fail(f"business registry lost the current operational repository: {current}")
        if target in registry_text:
            fail(f"business registry uses a target repository before cutover: {target}")

        repository_ids.add(repository_id)
        current_names.add(current)
        target_names.add(target)


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
