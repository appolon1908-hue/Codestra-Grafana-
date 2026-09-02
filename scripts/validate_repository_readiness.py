#!/usr/bin/env python3
"""Validate repository-only Grafana image release readiness."""
from __future__ import annotations
import json
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
IMAGE = re.compile(r"^[a-z0-9./_-]+@sha256:[0-9a-f]{64}$")
AUTHORITY = "appolon1908-hue/Codestra-Telemetry/.github/workflows/reusable-release-image.yml@9a6aebb849bbc068105c10d9d1dfd39ebf6f78bd"
REQUIRED = (
    "REPOSITORY_PROFILE.md", "SECURITY.md", ".github/CODEOWNERS",
    "docs/BACKUP_RESTORE_ROLLBACK.md", "docs/UPGRADE.md", ".dockerignore",
    ".gitleaks.toml", "codestra/release/image-build.v1.json",
    "codestra/release/runtime-base.lock.json", ".github/workflows/release-image.yml",
    "scripts/build_and_inspect_locked_image.sh", "scripts/validate_runtime_identity.py",
    "requirements-validation.txt",
)

def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")

def load(path: str) -> dict:
    value = json.loads((ROOT / path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path} must contain an object")
    return value

def main() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        fail(f"missing readiness files: {missing}")
    manifest = load("codestra/release/image-build.v1.json")
    lock = load("codestra/release/runtime-base.lock.json")
    if manifest.get("imageId") != "grafana" or manifest.get("context") != "." or manifest.get("productionActivation") is not False:
        fail("image manifest identity/context/activation mismatch")
    if lock.get("artifactModel") != "repository-configured-signed-image" or lock.get("productionActivation") is not False:
        fail("runtime lock model/activation mismatch")
    for field in ("buildFrontendImage", "builderImage", "upstreamImage"):
        if not IMAGE.fullmatch(str(lock.get(field, ""))):
            fail(f"mutable build input: {field}")
    if manifest.get("buildArgs") != {"GRAFANA_IMAGE": lock["upstreamImage"], "PYTHON_BUILDER_IMAGE": lock["builderImage"]}:
        fail("manifest build arguments mismatch")
    if lock.get("upstreamRelease") != "v13.2.1" or not re.fullmatch(r"[0-9a-f]{40}", str(lock.get("upstreamReleaseCommit", ""))):
        fail("official Grafana release authority mismatch")
    if lock.get("upstreamSignature") != {"available": False, "verification": "NO_OCI_SIGNATURE_OR_ATTESTATION_PUBLISHED"}:
        fail("upstream signature disposition mismatch")
    if lock.get("vendoredSourceExecutableUsed") is not False:
        fail("unreleased vendored source may not be executable authority")
    runtime_example = (ROOT / "codestra/deploy/runtime.env.example").read_text(encoding="utf-8")
    if "CODESTRA_GRAFANA_IMAGE=ghcr.io/appolon1908-hue/codestra-grafana--grafana@sha256:" not in runtime_example:
        fail("runtime example does not match reusable release registry identity")
    dockerfile = (ROOT / manifest["dockerfile"]).read_text(encoding="utf-8")
    if dockerfile.splitlines()[0] != f"# syntax={lock['buildFrontendImage']}":
        fail("Dockerfile frontend mismatch")
    for token in ("FROM ${PYTHON_BUILDER_IMAGE}", "FROM ${GRAFANA_IMAGE}", "runtime-base.lock.json", "USER 472:0"):
        if token not in dockerfile:
            fail(f"Dockerfile release boundary missing: {token}")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for token in ("upstream/", "codestra/dashboards/", ".git/"):
        if token not in dockerignore:
            fail(f"build context exclusion missing: {token}")
    release = yaml.safe_load((ROOT / ".github/workflows/release-image.yml").read_text(encoding="utf-8"))
    job = release.get("jobs", {}).get("release", {})
    if job.get("uses") != AUTHORITY or job.get("with", {}).get("image_id") != "grafana":
        fail("release authority mismatch")
    build_call = 'bash scripts/build_and_inspect_locked_image.sh "$GITHUB_SHA"'
    for relative in (".github/workflows/validate-repository-readiness.yml", ".github/workflows/validate-repository-readiness-protected.yml"):
        if build_call not in (ROOT / relative).read_text(encoding="utf-8"):
            fail(f"merge/protected image build missing: {relative}")
    compose = yaml.safe_load((ROOT / "codestra/deploy/compose.candidate.yaml").read_text(encoding="utf-8"))
    service = compose.get("services", {}).get("grafana", {})
    if "build" in service or service.get("privileged") is True or service.get("network_mode") == "host":
        fail("Grafana Compose is not a deploy-only hardened boundary")
    if service.get("ports") != ["127.0.0.1:${GRAFANA_HOST_PORT:-3000}:3000"]:
        fail("Grafana native listener is not loopback-only")
    runtime = load("codestra/runtime.v1.json")
    if runtime.get("status") != "CONFIG_PREPARED_NOT_DEPLOYED" or any(runtime.get("activation", {}).values()):
        fail("Grafana runtime activation must remain false")
    for workflow in (ROOT / ".github/workflows").glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        for reference in re.findall(r"(?m)^\s*(?:-\s*)?uses:\s*([^\s#]+)", text):
            if not reference.startswith("./") and not re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", reference):
                fail(f"mutable action: {workflow.name}: {reference}")
        if re.search(r"git push\s+origin\s+HEAD:(?:main|development|test|staging|production)", text):
            fail(f"direct protected-branch push: {workflow.name}")
    print("GRAFANA_REPOSITORY_READINESS_SOURCE=PASS")
    print("ARTIFACT_MODEL=SIGNED_DERIVED_IMAGE")
    print("PRODUCTION_ACTIVATION=NO")

if __name__ == "__main__":
    main()
