from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "codestra_observability_authority",
    ROOT / "scripts" / "validate_codestra_observability.py",
)
assert SPEC is not None and SPEC.loader is not None
AUTHORITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTHORITY)


class PrivatePostgresAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(
            (
                ROOT / "governance" / "private-service-authority.v1.json"
            ).read_text(encoding="utf-8")
        )

    def test_publication_flags_are_fail_closed(self) -> None:
        for field in ("caddy_publication_allowed", "kong_publication_allowed"):
            changed = copy.deepcopy(self.document)
            changed["postgres_exporter"][field] = True
            with self.subTest(field=field), self.assertRaises(SystemExit):
                AUTHORITY.validate_postgres_exporter_document(changed)

    def test_forbidden_hostname_comparison_is_case_insensitive(self) -> None:
        retired = "PGEX" + ".CODESTRA.MEDIA"
        self.assertTrue(AUTHORITY.contains_forbidden_postgres_hostname(retired))

    def test_generated_bytecode_is_excluded_from_source_scan(self) -> None:
        self.assertTrue(
            AUTHORITY.is_ignored_source_path(
                ROOT / "scripts" / "__pycache__" / "validator.cpython-312.pyc"
            )
        )


class GeneratedDashboardValidationOrderTests(unittest.TestCase):
    def test_governed_scan_runs_after_dashboard_generation(self) -> None:
        events: list[str] = []

        class FakeCore:
            def validate_hostnames(self) -> None:
                events.append("scan")

            def validate_generated_dashboards(self, _data: dict) -> None:
                events.append("generate")

            def main(self) -> None:
                self.validate_hostnames()
                self.validate_generated_dashboards({})

        core = FakeCore()
        with (
            patch.object(AUTHORITY, "load_core", return_value=core),
            patch.object(AUTHORITY, "validate_postgres_exporter_authority"),
            patch.object(AUTHORITY, "validate_repository_aliases"),
        ):
            AUTHORITY.main()

        self.assertEqual(events, ["scan", "generate", "scan"])


class RepositoryAliasAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(
            (ROOT / "governance" / "repository-name-aliases.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.registry_text = (ROOT / "codestra" / "business-registry.json").read_text(
            encoding="utf-8"
        )

    def test_exact_governed_alias_set_is_required(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["mappings"].pop()
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_repository_alias_document(changed, self.registry_text)

    def test_alias_names_are_bound_to_stable_repository_id(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["mappings"][0]["current_repository"] = (
            "appolon1908-hue/unreviewed-alias"
        )
        changed_registry = self.registry_text + " appolon1908-hue/unreviewed-alias"
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_repository_alias_document(changed, changed_registry)

    def test_registry_repository_comparison_is_exact(self) -> None:
        registry = json.loads(self.registry_text)
        restaurant = next(
            item
            for business in registry["businesses"]
            for item in business["repositories"]
            if item["repo"] == "appolon1908-hue/Frontend-Resturant-"
        )
        restaurant["repo"] = "appolon1908-hue/Frontend-Resturant--renamed"
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_repository_alias_document(
                self.document,
                json.dumps(registry),
            )

    def test_non_operational_metadata_cannot_mask_removed_repository(self) -> None:
        registry = json.loads(self.registry_text)
        restaurant = next(
            item
            for business in registry["businesses"]
            for item in business["repositories"]
            if item["repo"] == "appolon1908-hue/Frontend-Resturant-"
        )
        restaurant["repo"] = "appolon1908-hue/unapproved-restaurant-frontend"
        registry.setdefault("platform_services", []).append(
            {"repo": "appolon1908-hue/Frontend-Resturant-"}
        )
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_repository_alias_document(
                self.document,
                json.dumps(registry),
            )


if __name__ == "__main__":
    unittest.main()
