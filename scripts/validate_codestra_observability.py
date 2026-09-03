#!/usr/bin/env python3
"""Governed entry point for the Codestra Grafana corporate validator.

The full pre-existing validator is preserved as an exact core blob. This entry
point removes the retired public PostgreSQL Exporter hostname before compiling
that core, then adds fail-closed checks for the private service authority and
repository-name migration aliases.
"""

from __future__ import annotations

import html
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Iterator
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "validator_core" / "validate_codestra_observability_core.py"
POSTGRES_POLICY = ROOT / "governance" / "private-service-authority.v1.json"
REPOSITORY_ALIASES = ROOT / "governance" / "repository-name-aliases.v1.json"
BUSINESS_REGISTRY = ROOT / "codestra" / "business-registry.json"
DASHBOARDS = ROOT / "codestra" / "dashboards"
FORBIDDEN_POSTGRES_HOST = "pgex" + ".codestra.media"
PRIVATE_POSTGRES_IDENTITY = "postgres-exporter:9187"
DOT_EQUIVALENTS = str.maketrans({"\u3002": ".", "\uff0e": ".", "\uff61": "."})
REQUIRED_REPOSITORY_ALIASES = {
    1221155447: {
        "current": "appolon1908-hue/Frontend-Resturant-",
        "target": "appolon1908-hue/restaurant-frontend",
        "business": "restaurant",
        "service": "restaurant-frontend",
        "profile": "frontend",
    },
    1343761049: {
        "current": "appolon1908-hue/transportaion-Frontend",
        "target": "appolon1908-hue/freight-platform-frontend",
        "business": "transportation",
        "service": "transportation-frontend",
        "profile": "frontend",
    },
    1343962199: {
        "current": "appolon1908-hue/LARIM-A-Fornt-end",
        "target": "appolon1908-hue/LARIM-A-Frontend",
        "business": "larim-a",
        "service": "larim-a-frontend",
        "profile": "frontend",
    },
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_text(text: str, source: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_unique_json_object)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        fail(f"invalid JSON {source}: {exc}")


def load_json(path: Path) -> Any:
    return load_json_text(
        path.read_text(encoding="utf-8"),
        str(path.relative_to(ROOT)),
    )


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


def normalized_hostname_text(text: str) -> str:
    """Normalize URL/IDNA representations that resolve to the same hostname."""

    normalized = html.unescape(text).translate(DOT_EQUIVALENTS)
    for _ in range(4):
        decoded = html.unescape(unquote(normalized)).translate(DOT_EQUIVALENTS)
        if decoded == normalized:
            break
        normalized = decoded
    return normalized.lower()


def contains_forbidden_postgres_hostname(text: str) -> bool:
    return FORBIDDEN_POSTGRES_HOST in normalized_hostname_text(text)


def iter_decoded_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str):
                yield key
            yield from iter_decoded_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_decoded_strings(child)


def validate_decoded_json_hostnames(document: Any, source: str) -> None:
    for value in iter_decoded_strings(document):
        if contains_forbidden_postgres_hostname(value):
            fail(
                "retired PostgreSQL Exporter public hostname remains in decoded "
                f"JSON content: {source}"
            )


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
    if not isinstance(document, dict):
        fail("private service authority root must be an object")
    if document.get("schema_version") != "1.0":
        fail("private service authority schema_version must be 1.0")
    if document.get("status") != "ACTIVE_SOURCE_AUTHORITY":
        fail("private service authority must be active")

    service = document.get("postgres_exporter", {})
    if not isinstance(service, dict):
        fail("PostgreSQL Exporter authority must be an object")
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


def registry_operational_records(registry_text: str) -> list[dict[str, str]]:
    registry = load_json_text(registry_text, "codestra/business-registry.json")
    if not isinstance(registry, dict):
        fail("business registry root must be an object")

    businesses = registry.get("businesses")
    if not isinstance(businesses, list):
        fail("business registry businesses must be a list")

    records: list[dict[str, str]] = []
    for business in businesses:
        if not isinstance(business, dict):
            fail("business registry contains a non-object business")
        business_id = business.get("id")
        if not isinstance(business_id, str) or not business_id:
            fail("business registry contains an invalid business ID")
        operational = business.get("repositories")
        if not isinstance(operational, list):
            fail("business registry business repositories must be a list")
        for item in operational:
            if not isinstance(item, dict):
                fail("business registry contains a non-object repository record")
            repository = item.get("repo")
            service = item.get("service")
            profile = item.get("profile")
            if not all(
                isinstance(value, str) and value
                for value in (repository, service, profile)
            ):
                fail("business registry operational repository record is incomplete")
            records.append(
                {
                    "business": business_id,
                    "repo": repository,
                    "service": service,
                    "profile": profile,
                }
            )
    return records


def registry_repositories(registry_text: str) -> set[str]:
    """Compatibility helper returning operational business repositories only."""

    return {record["repo"] for record in registry_operational_records(registry_text)}


def validate_repository_alias_document(document: Any, registry_text: str) -> None:
    if not isinstance(document, dict):
        fail("repository alias authority root must be an object")
    if document.get("schema_version") != "1.0":
        fail("repository alias schema_version must be 1.0")
    if document.get("status") != "PREPARED_NOT_RENAMED":
        fail("Grafana repository aliases must remain prepared until GitHub cutover")

    mappings = document.get("mappings", [])
    if not isinstance(mappings, list) or not mappings:
        fail("repository alias mappings are empty or invalid")
    records = registry_operational_records(registry_text)

    repository_ids: set[int] = set()
    current_names: set[str] = set()
    target_names: set[str] = set()
    for mapping in mappings:
        if not isinstance(mapping, dict):
            fail("repository alias contains a non-object mapping")
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

        expected = REQUIRED_REPOSITORY_ALIASES.get(repository_id)
        if expected is None:
            fail(f"unexpected governed repository alias ID: {repository_id}")
        if current != expected["current"] or target != expected["target"]:
            fail(
                "repository alias identity changed for stable ID "
                f"{repository_id}"
            )

        current_records = [record for record in records if record["repo"] == current]
        if current_records != [
            {
                "business": expected["business"],
                "repo": expected["current"],
                "service": expected["service"],
                "profile": expected["profile"],
            }
        ]:
            fail(
                "business registry repository binding changed for stable ID "
                f"{repository_id}: {current_records}"
            )
        if any(record["repo"] == target for record in records):
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


def validate_repository_aliases() -> None:
    document = load_json(REPOSITORY_ALIASES)
    registry_text = BUSINESS_REGISTRY.read_text(encoding="utf-8")
    validate_repository_alias_document(document, registry_text)


def validate_generated_dashboard_authority() -> None:
    files = sorted(DASHBOARDS.rglob("*.json"))
    if not files:
        fail("generated dashboard portfolio is empty")
    for path in files:
        document = load_json(path)
        validate_decoded_json_hostnames(document, str(path.relative_to(ROOT)))


def main() -> None:
    core = load_core()
    original_validate_hostnames = core.validate_hostnames
    original_validate_generated_dashboards = core.validate_generated_dashboards

    def governed_validate_hostnames() -> None:
        original_validate_hostnames()
        validate_postgres_exporter_authority()
        validate_repository_aliases()

    def governed_validate_generated_dashboards(data: dict[str, Any]) -> None:
        original_validate_generated_dashboards(data)
        # The generator can construct strings or encoded URL hostnames after
        # the initial source scan. Re-run governed checks and inspect decoded,
        # percent-decoded, HTML-decoded, and IDNA-dot-normalized strings before
        # the core validator can print PASS.
        governed_validate_hostnames()
        validate_generated_dashboard_authority()

    core.validate_hostnames = governed_validate_hostnames
    core.validate_generated_dashboards = governed_validate_generated_dashboards
    core.main()


if __name__ == "__main__":
    main()
