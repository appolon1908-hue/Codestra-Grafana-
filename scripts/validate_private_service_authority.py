#!/usr/bin/env python3
"""Validate Grafana's private-service and repository-name authorities."""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "governance" / "private-service-authority.v1.json"
ALIASES = ROOT / "governance" / "repository-name-aliases.v1.json"
REGISTRY = ROOT / "codestra" / "business-registry.json"
DASHBOARDS = ROOT / "codestra" / "dashboards"
LEGACY_VALIDATOR = ROOT / "scripts" / "validate_codestra_observability.py"
FORBIDDEN_HOST = "pgex" + ".codestra.media"
PRIVATE_IDENTITY = "postgres-exporter:9187"
DOT_EQUIVALENTS = str.maketrans({"\u3002": ".", "\uff0e": ".", "\uff61": "."})
EXPECTED_ALIASES = {
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
TEXT_SUFFIXES = {
    ".cfg", ".conf", ".env", ".hcl", ".ini", ".json", ".md", ".py",
    ".sh", ".tf", ".toml", ".yaml", ".yml",
}
SCAN_ROOTS = (
    ROOT / "codestra",
    ROOT / ".github" / "workflows",
    ROOT / "governance",
    ROOT / "integration",
    ROOT / "scripts",
    ROOT / "tests",
)


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


def load_json_text(text: str, source: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        fail(f"invalid JSON in {source}: {exc}")


def load_json(path: Path) -> Any:
    if not path.is_file():
        fail(f"required authority file is missing: {path.relative_to(ROOT)}")
    return load_json_text(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))


def normalize_hostname_text(value: str) -> str:
    normalized = html.unescape(value).translate(DOT_EQUIVALENTS)
    for _ in range(4):
        decoded = html.unescape(unquote(normalized)).translate(DOT_EQUIVALENTS)
        if decoded == normalized:
            break
        normalized = decoded
    return normalized.lower()


def contains_forbidden_hostname(value: str) -> bool:
    return FORBIDDEN_HOST in normalize_hostname_text(value)


def iter_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str):
                yield key
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def validate_decoded_strings(value: Any, source: str) -> None:
    for text in iter_strings(value):
        if contains_forbidden_hostname(text):
            fail(f"retired public exporter hostname remains in decoded source: {source}")


def validate_policy(document: Any) -> None:
    if not isinstance(document, dict):
        fail("private-service authority root must be an object")
    if document.get("schema_version") != "1.0":
        fail("private-service authority schema_version must be 1.0")
    if document.get("status") != "ACTIVE_SOURCE_AUTHORITY":
        fail("private-service authority must be active")
    exporter = document.get("postgres_exporter")
    if not isinstance(exporter, dict):
        fail("PostgreSQL Exporter authority must be an object")
    expected = {
        "repository_id": 1350839865,
        "repository": "appolon1908-hue/Codestra-Postgres-Exporter",
        "public_hostname": None,
        "private_service_identity": PRIVATE_IDENTITY,
        "forbidden_public_hostname": FORBIDDEN_HOST,
        "exposure": "PRIVATE_INTERNAL_ONLY",
        "caddy_publication_allowed": False,
        "kong_publication_allowed": False,
        "host_public_port_allowed": False,
        "grafana_browser_access_allowed": False,
    }
    for key, expected_value in expected.items():
        if exporter.get(key) != expected_value:
            fail(f"PostgreSQL Exporter authority drifted: {key}")


def registry_records(document: Any) -> list[dict[str, str]]:
    if not isinstance(document, dict):
        fail("business registry root must be an object")
    businesses = document.get("businesses")
    if not isinstance(businesses, list):
        fail("business registry businesses must be a list")
    records: list[dict[str, str]] = []
    for business in businesses:
        if not isinstance(business, dict) or not isinstance(business.get("id"), str):
            fail("business registry contains an invalid business")
        repositories = business.get("repositories")
        if not isinstance(repositories, list):
            fail("business registry contains an invalid repository inventory")
        for repository in repositories:
            if not isinstance(repository, dict):
                fail("business registry contains a non-object repository")
            values = {
                "business": business["id"],
                "repo": repository.get("repo"),
                "service": repository.get("service"),
                "profile": repository.get("profile"),
            }
            if not all(isinstance(value, str) and value for value in values.values()):
                fail("business registry contains an incomplete repository record")
            records.append(values)
    return records


def validate_aliases(document: Any, registry: Any) -> None:
    if not isinstance(document, dict):
        fail("repository alias authority root must be an object")
    if document.get("schema_version") != "1.0":
        fail("repository alias schema_version must be 1.0")
    if document.get("status") != "PREPARED_NOT_RENAMED":
        fail("repository aliases changed state without a controlled cutover")
    if document.get("identity_key") != "repository_id":
        fail("repository_id must remain the alias identity key")
    mappings = document.get("mappings")
    if not isinstance(mappings, list) or len(mappings) != len(EXPECTED_ALIASES):
        fail("repository alias inventory is incomplete")
    records = registry_records(registry)
    seen: set[int] = set()
    for mapping in mappings:
        if not isinstance(mapping, dict):
            fail("repository alias contains a non-object mapping")
        repository_id = mapping.get("repository_id")
        if repository_id in seen or repository_id not in EXPECTED_ALIASES:
            fail(f"repository alias ID is duplicate or unexpected: {repository_id}")
        seen.add(repository_id)
        expected = EXPECTED_ALIASES[repository_id]
        if mapping.get("current_repository") != expected["current"]:
            fail(f"current repository drifted for stable ID {repository_id}")
        if mapping.get("target_repository_after_cutover") != expected["target"]:
            fail(f"target repository drifted for stable ID {repository_id}")
        if mapping.get("status") != "PREPARED_NOT_RENAMED":
            fail(f"repository alias changed state for stable ID {repository_id}")
        matching = [record for record in records if record["repo"] == expected["current"]]
        required_record = {
            "business": expected["business"],
            "repo": expected["current"],
            "service": expected["service"],
            "profile": expected["profile"],
        }
        if matching != [required_record]:
            fail(f"business registry binding drifted for stable ID {repository_id}")
        if any(record["repo"] == expected["target"] for record in records):
            fail(f"future repository target is operational before cutover: {expected['target']}")


def ignored(path: Path) -> bool:
    return (
        path.suffix.lower() not in TEXT_SUFFIXES
        or ".git" in path.parts
        or "__pycache__" in path.parts
        or path.suffix.lower() == ".pyc"
    )


def validate_active_source() -> None:
    exemptions = {POLICY.resolve(), LEGACY_VALIDATOR.resolve()}
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or ignored(path) or path.resolve() in exemptions:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if path.suffix.lower() == ".json":
                validate_decoded_strings(
                    load_json_text(text, str(path.relative_to(ROOT))),
                    str(path.relative_to(ROOT)),
                )
            elif contains_forbidden_hostname(text):
                fail(f"retired public exporter hostname remains in active source: {path.relative_to(ROOT)}")


def validate_generated_dashboards() -> None:
    if not DASHBOARDS.exists():
        return
    for path in sorted(DASHBOARDS.rglob("*.json")):
        validate_decoded_strings(load_json(path), str(path.relative_to(ROOT)))


def main() -> None:
    validate_policy(load_json(POLICY))
    validate_aliases(load_json(ALIASES), load_json(REGISTRY))
    validate_active_source()
    validate_generated_dashboards()
    print("Grafana private-service and repository-name authority: PASS")


if __name__ == "__main__":
    main()
