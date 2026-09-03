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

    def test_decoded_json_hostname_is_rejected(self) -> None:
        raw = r'{"url":"pgex\u002ecodestra.media"}'
        self.assertFalse("pgex.codestra.media" in raw.lower())
        document = AUTHORITY.load_json_text(raw, "synthetic-dashboard.json")
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_decoded_json_hostnames(
                document,
                "synthetic-dashboard.json",
            )

    def test_percent_encoded_hostname_is_rejected(self) -> None:
        encoded = "https://" + "pgex" + "%2e" + "codestra.media/metrics"
        self.assertTrue(AUTHORITY.contains_forbidden_postgres_hostname(encoded))

    def test_double_percent_encoded_hostname_is_rejected(self) -> None:
        encoded = "https://" + "pgex" + "%252e" + "codestra.media/metrics"
        self.assertTrue(AUTHORITY.contains_forbidden_postgres_hostname(encoded))

    def test_html_encoded_hostname_is_rejected(self) -> None:
        encoded = "https://" + "pgex" + "&#46;" + "codestra.media/metrics"
        self.assertTrue(AUTHORITY.contains_forbidden_postgres_hostname(encoded))

    def test_idna_dot_equivalent_hostname_is_rejected(self) -> None:
        encoded = "pgex" + "\u3002" + "codestra.media"
        self.assertTrue(AUTHORITY.contains_forbidden_postgres_hostname(encoded))

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            AUTHORITY.load_json_text(
                '{"public_hostname":"public.example","public_hostname":null}',
                "synthetic-authority.json",
            )

    def test_generated_bytecode_is_excluded_from_source_scan(self) -> None:
        self.assertTrue(
            AUTHORITY.is_ignored_source_path(
                ROOT / "scripts" / "__pycache__" / "validator.cpython-312.pyc"
            )
        )


class GeneratedDashboardValidationOrderTests(unittest.TestCase):
    def test_governed_and_decoded_scans_run_after_dashboard_generation(self) -> None:
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
            patch.object(
                AUTHORITY,
                "validate_generated_dashboard_authority",
                side_effect=lambda: events.append("decoded"),
            ),
        ):
            AUTHORITY.main()

        self.assertEqual(events, ["scan", "generate", "scan", "decoded"])


class RepositoryAliasAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(
            (ROOT / "governance" / "repository-name-aliases.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.registry = json.loads(
            (ROOT / "codestra" / "business-registry.json").read_text(
                encoding="utf-8"
            )
        )
        self.registry_text = json.dumps(self.registry)

    @staticmethod
    def restaurant_record(registry: dict) -> dict:
        return next(
            item
            for business in registry["businesses"]
            for item in business["repositories"]
            if item["repo"] == "appolon1908-hue/Frontend-Resturant-"
        )

    def test_exact_governed_alias_set_is_required(self) -> None:
        changed = copy.deepcopy(self.document)
        changed["mappings"].pop()
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_repository_alias_document(changed, self.registry_text)

    def test_alias_names_are_bound_to_stable_repository_id_with_valid_json(self) -> None:
        changed_aliases = copy.deepcopy(self.document)
        changed_registry = copy.deepcopy(self.registry)
        unreviewed = "appolon1908-hue/unreviewed-alias"
        changed_aliases["mappings"][0]["current_repository"] = unreviewed
        self.restaurant_record(changed_registry)["repo"] = unreviewed

        with self.assertRaises(SystemExit):
            AUTHORITY.validate_repository_alias_document(
                changed_aliases,
                json.dumps(changed_registry),
            )

    def test_alias_is_bound_to_expected_business(self) -> None:
        changed = copy.deepcopy(self.registry)
        restaurant_business = next(
            item for item in changed["businesses"] if item["id"] == "restaurant"
        )
        codestra_business = next(
            item for item in changed["businesses"] if item["id"] == "codestra"
        )
        restaurant_record = next(
            item
            for item in restaurant_business["repositories"]
            if item["repo"] == "appolon1908-hue/Frontend-Resturant-"
        )
        other_record = codestra_business["repositories"][0]
        restaurant_record["repo"], other_record["repo"] = (
            other_record["repo"],
            restaurant_record["repo"],
        )

        with self.assertRaises(SystemExit):
            AUTHORITY.validate_repository_alias_document(
                self.document,
                json.dumps(changed),
            )

    def test_alias_is_bound_to_expected_service(self) -> None:
        changed = copy.deepcopy(self.registry)
        self.restaurant_record(changed)["service"] = "unapproved-restaurant-service"
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_repository_alias_document(
                self.document,
                json.dumps(changed),
            )

    def test_alias_is_bound_to_expected_profile(self) -> None:
        changed = copy.deepcopy(self.registry)
        self.restaurant_record(changed)["profile"] = "backend"
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_repository_alias_document(
                self.document,
                json.dumps(changed),
            )

    def test_registry_repository_comparison_is_exact(self) -> None:
        changed = copy.deepcopy(self.registry)
        self.restaurant_record(changed)["repo"] = (
            "appolon1908-hue/Frontend-Resturant--renamed"
        )
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_repository_alias_document(
                self.document,
                json.dumps(changed),
            )

    def test_non_operational_metadata_cannot_mask_removed_repository(self) -> None:
        changed = copy.deepcopy(self.registry)
        self.restaurant_record(changed)["repo"] = (
            "appolon1908-hue/unapproved-restaurant-frontend"
        )
        changed.setdefault("platform_services", []).append(
            {"repo": "appolon1908-hue/Frontend-Resturant-"}
        )
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_repository_alias_document(
                self.document,
                json.dumps(changed),
            )


if __name__ == "__main__":
    unittest.main()
