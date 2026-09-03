from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "private_service_authority",
    ROOT / "scripts" / "validate_private_service_authority.py",
)
assert SPEC is not None and SPEC.loader is not None
AUTHORITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTHORITY)


class PrivateServiceAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = AUTHORITY.load_json(AUTHORITY.POLICY)
        self.aliases = AUTHORITY.load_json(AUTHORITY.ALIASES)
        self.registry = AUTHORITY.load_json(AUTHORITY.REGISTRY)

    def test_current_authority_passes(self) -> None:
        AUTHORITY.validate_policy(self.policy)
        AUTHORITY.validate_aliases(self.aliases, self.registry)

    def test_every_publication_path_is_fail_closed(self) -> None:
        for field in (
            "caddy_publication_allowed",
            "kong_publication_allowed",
            "host_public_port_allowed",
            "grafana_browser_access_allowed",
        ):
            changed = copy.deepcopy(self.policy)
            changed["postgres_exporter"][field] = True
            with self.subTest(field=field), self.assertRaises(SystemExit):
                AUTHORITY.validate_policy(changed)

    def test_public_hostname_is_denied(self) -> None:
        changed = copy.deepcopy(self.policy)
        changed["postgres_exporter"]["public_hostname"] = "metrics.example.test"
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_policy(changed)

    def test_encoded_retired_hostname_is_denied(self) -> None:
        variants = (
            "https://" + "pgex" + "%2e" + "codestra.media/metrics",
            "https://" + "pgex" + "%252e" + "codestra.media/metrics",
            "https://" + "pgex" + "&#46;" + "codestra.media/metrics",
            "pgex" + "\u3002" + "codestra.media",
        )
        for value in variants:
            with self.subTest(value=value):
                self.assertTrue(AUTHORITY.contains_forbidden_hostname(value))

    def test_json_escaped_retired_hostname_is_denied_after_decode(self) -> None:
        document = AUTHORITY.load_json_text(
            r'{"url":"pgex\u002ecodestra.media"}',
            "synthetic.json",
        )
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_decoded_strings(document, "synthetic.json")

    def test_duplicate_json_keys_are_denied(self) -> None:
        with self.assertRaises(SystemExit):
            AUTHORITY.load_json_text(
                '{"public_hostname":"public.example","public_hostname":null}',
                "synthetic.json",
            )

    def test_alias_set_cannot_be_reduced(self) -> None:
        changed = copy.deepcopy(self.aliases)
        changed["mappings"].pop()
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_aliases(changed, self.registry)

    def test_alias_name_is_bound_to_stable_id(self) -> None:
        changed = copy.deepcopy(self.aliases)
        changed["mappings"][0]["current_repository"] = (
            "appolon1908-hue/unapproved-restaurant"
        )
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_aliases(changed, self.registry)

    def _restaurant_record(self, registry: dict) -> dict:
        return next(
            record
            for business in registry["businesses"]
            for record in business["repositories"]
            if record["repo"] == "appolon1908-hue/Frontend-Resturant-"
        )

    def test_business_service_and_profile_bindings_are_independent(self) -> None:
        for field, value in (
            ("service", "unapproved-service"),
            ("profile", "backend"),
        ):
            changed = copy.deepcopy(self.registry)
            self._restaurant_record(changed)[field] = value
            with self.subTest(field=field), self.assertRaises(SystemExit):
                AUTHORITY.validate_aliases(self.aliases, changed)

    def test_future_target_cannot_become_operational_early(self) -> None:
        changed = copy.deepcopy(self.registry)
        self._restaurant_record(changed)["repo"] = (
            "appolon1908-hue/restaurant-frontend"
        )
        with self.assertRaises(SystemExit):
            AUTHORITY.validate_aliases(self.aliases, changed)


if __name__ == "__main__":
    unittest.main()
