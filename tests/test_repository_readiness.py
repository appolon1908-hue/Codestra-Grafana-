from __future__ import annotations
import json
import os
import subprocess
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]

class ReadinessTests(unittest.TestCase):
    def test_validator(self) -> None:
        subprocess.run(["python3", "scripts/validate_repository_readiness.py"], cwd=ROOT, check=True)

    def test_runtime_remains_inactive(self) -> None:
        runtime = json.loads((ROOT / "codestra/runtime.v1.json").read_text())
        self.assertTrue(runtime["activation"])
        self.assertTrue(all(value is False for value in runtime["activation"].values()))

    def test_compose_is_deploy_only_and_file_secret_bound(self) -> None:
        compose = yaml.safe_load((ROOT / "codestra/deploy/compose.candidate.yaml").read_text())
        service = compose["services"]["grafana"]
        self.assertNotIn("build", service)
        self.assertTrue(service["image"].startswith("${CODESTRA_GRAFANA_IMAGE:"))
        self.assertTrue(all(set(value) == {"file"} for value in compose["secrets"].values()))

    def test_official_release_and_images_are_exact(self) -> None:
        lock = json.loads((ROOT / "codestra/release/runtime-base.lock.json").read_text())
        self.assertEqual(lock["upstreamReleaseCommit"], "56cd3e9288d8255fecebe5d05b48d191f50674b5")
        self.assertRegex(lock["upstreamImage"], r"@sha256:[0-9a-f]{64}$")
        self.assertFalse(lock["vendoredSourceExecutableUsed"])

    def test_runtime_identity_rejects_mutable_or_misaligned_images(self) -> None:
        base = dict(os.environ)
        base.update(
            CODESTRA_SOURCE_SHA="0" * 40,
            CODESTRA_IMAGE_DIGEST="sha256:" + "2" * 64,
        )
        for image in (
            "ghcr.io/appolon1908-hue/codestra-grafana--grafana:latest",
            "ghcr.io/appolon1908-hue/codestra-grafana--grafana@sha256:" + "1" * 64,
        ):
            result = subprocess.run(
                ["python3", "scripts/validate_runtime_identity.py"],
                cwd=ROOT,
                env={**base, "CODESTRA_GRAFANA_IMAGE": image},
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)

if __name__ == "__main__":
    unittest.main()
