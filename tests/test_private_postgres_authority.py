from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


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
        self.assertTrue(
            AUTHORITY.contains_forbidden_postgres_hostname(retired)
        )


if __name__ == "__main__":
    unittest.main()
