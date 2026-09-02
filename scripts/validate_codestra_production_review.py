#!/usr/bin/env python3
"""Fail-closed validation for Grafana production-review remediations."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "codestra" / "deploy" / "compose.candidate.yaml"
DOCKERFILE = ROOT / "codestra" / "deploy" / "Dockerfile"
HARDENER = ROOT / "scripts" / "harden_codestra_dashboards.py"
PROVISIONING = ROOT / "codestra" / "provisioning"
GENERATED = ROOT / "codestra" / "dashboards"
ODOO_SUCCESS_THRESHOLDS = [
    {"color": "red", "value": None},
    {"color": "orange", "value": 95},
    {"color": "green", "value": 99},
]
IMAGE_VARIABLES = (
    ("PYTHON_BUILDER_IMAGE_NAME", "PYTHON_BUILDER_IMAGE_DIGEST"),
    ("GRAFANA_BASE_IMAGE_NAME", "GRAFANA_BASE_IMAGE_DIGEST"),
    ("CODESTRA_GRAFANA_IMAGE_NAME", "CODESTRA_GRAFANA_IMAGE_DIGEST"),
)
MUTATION_PANEL_TYPES = {"button", "actions", "form-panel"}
FORBIDDEN_QUERY_TOKENS = (
    "tenant_id=",
    "tenant_id=~",
    "customer_id=",
    "customer_id=~",
    "account_id=",
    "account_id=~",
    "user_id=",
    "user_id=~",
)


def fail(message: str) -> None:
    print(f"GRAFANA_PRODUCTION_REVIEW_ERROR={message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot parse {path.relative_to(ROOT)}: {exc}")
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain an object")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        fail(f"cannot parse {path.relative_to(ROOT)}: {exc}")
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain an object")
    return value


def validate_image_contract() -> None:
    compose = load_yaml(COMPOSE)
    service = compose.get("services", {}).get("grafana", {})
    build_args = service.get("build", {}).get("args", {})
    expressions = {
        "PYTHON_BUILDER_IMAGE": build_args.get("PYTHON_BUILDER_IMAGE"),
        "GRAFANA_IMAGE": build_args.get("GRAFANA_IMAGE"),
        "CODESTRA_GRAFANA_IMAGE": service.get("image"),
    }
    expected = {
        "PYTHON_BUILDER_IMAGE": (
            "PYTHON_BUILDER_IMAGE_NAME",
            "PYTHON_BUILDER_IMAGE_DIGEST",
        ),
        "GRAFANA_IMAGE": ("GRAFANA_BASE_IMAGE_NAME", "GRAFANA_BASE_IMAGE_DIGEST"),
        "CODESTRA_GRAFANA_IMAGE": (
            "CODESTRA_GRAFANA_IMAGE_NAME",
            "CODESTRA_GRAFANA_IMAGE_DIGEST",
        ),
    }
    for key, (name_var, digest_var) in expected.items():
        expression = str(expressions.get(key, ""))
        pattern = re.compile(
            rf"^\$\{{{name_var}:\?[^}}]+\}}@sha256:"
            rf"\$\{{{digest_var}:\?[^}}]+\}}$"
        )
        if pattern.fullmatch(expression) is None:
            fail(f"{key} must structurally separate image name and sha256 digest")

    for name_var, digest_var in IMAGE_VARIABLES:
        name = os.environ.get(name_var, "")
        digest = os.environ.get(digest_var, "")
        if not name or "@" in name or any(char.isspace() for char in name):
            fail(f"invalid immutable image name variable: {name_var}")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            fail(f"invalid sha256 digest variable: {digest_var}")


def validate_packaged_dashboard_pipeline() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    required = (
        "COPY scripts/harden_codestra_dashboards.py scripts/harden_codestra_dashboards.py",
        "COPY codestra/provisioning/ codestra/provisioning/",
        "python3 scripts/harden_codestra_dashboards.py",
        "COPY --from=dashboard-builder --chown=472:0 codestra/provisioning/ /etc/grafana/provisioning/",
        "COPY --from=dashboard-builder --chown=472:0 codestra/dashboards/ /etc/grafana/codestra-dashboards/",
    )
    for fragment in required:
        if fragment not in dockerfile:
            fail(f"Dockerfile omits final dashboard hardening control: {fragment}")


def validate_provisioning_tree(root: Path) -> None:
    dashboard_provisioning = root / "codestra" / "provisioning" / "dashboards"
    files = sorted(dashboard_provisioning.glob("*.yml"))
    if not files:
        fail("dashboard provisioning files are missing")

    intake_provider_found = False
    for path in files:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or document.get("apiVersion") != 1:
            fail(f"invalid dashboard provisioning document: {path}")
        providers = document.get("providers")
        if not isinstance(providers, list) or not providers:
            fail(f"dashboard provisioning providers are missing: {path}")
        for provider in providers:
            if not isinstance(provider, dict):
                fail(f"dashboard provider must be an object: {path}")
            if provider.get("type") != "file":
                fail(f"dashboard provider must be file based: {path}")
            if provider.get("disableDeletion") is not True:
                fail(f"dashboard deletion must be disabled: {path}")
            if provider.get("allowUiUpdates") is not False:
                fail(f"dashboard UI updates must be disabled: {path}")
            target = str(provider.get("options", {}).get("path", ""))
            if not target.startswith("/etc/grafana/"):
                fail(f"dashboard provider target is not immutable: {path}")
            if provider.get("folderUid") == "codestra-intake":
                intake_provider_found = True
                if target != "/etc/grafana/provisioning/intake-dashboards":
                    fail("intake provider target does not match the packaged dashboard tree")
    if not intake_provider_found:
        fail("Codestra intake dashboard provider is not validated")

    intake_root = root / "codestra" / "provisioning" / "intake-dashboards"
    intake_files = sorted(intake_root.rglob("*.json"))
    if not intake_files:
        fail("intake dashboard JSON files are missing")

    odoo_panels = 0
    for path in intake_files:
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(dashboard, dict):
            fail(f"intake dashboard must be an object: {path}")
        if dashboard.get("editable") is not False:
            fail(f"intake dashboard must be read-only: {path}")
        if int(dashboard.get("schemaVersion", 0)) < 39:
            fail(f"intake dashboard schema is outdated: {path}")
        if dashboard.get("links") not in ([], None):
            fail(f"intake dashboard may not contain action links: {path}")
        panels = dashboard.get("panels")
        if not isinstance(panels, list) or not panels:
            fail(f"intake dashboard has no panels: {path}")
        for panel in panels:
            if not isinstance(panel, dict):
                fail(f"intake panel must be an object: {path}")
            if panel.get("type") in MUTATION_PANEL_TYPES:
                fail(f"intake dashboard contains a mutation-capable panel: {path}")
            if panel.get("title") == "Odoo delivery success":
                odoo_panels += 1
                thresholds = (
                    panel.get("fieldConfig", {})
                    .get("defaults", {})
                    .get("thresholds", {})
                )
                if thresholds.get("mode") != "absolute":
                    fail("Odoo delivery success thresholds must be absolute")
                if thresholds.get("steps") != ODOO_SUCCESS_THRESHOLDS:
                    fail("Odoo delivery success thresholds reverse healthy status")
        serialized = json.dumps(dashboard, sort_keys=True).lower()
        for token in FORBIDDEN_QUERY_TOKENS:
            if token in serialized:
                fail(f"intake dashboard contains forbidden query token {token}: {path}")
    if odoo_panels != 1:
        fail(f"expected exactly one Odoo delivery success panel, found {odoo_panels}")


def validate_hardened_generated_dashboards(root: Path) -> None:
    files = sorted((root / "codestra" / "dashboards").rglob("*.json"))
    backlog_panels = 0
    for path in files:
        dashboard = json.loads(path.read_text(encoding="utf-8"))
        for panel in dashboard.get("panels", []):
            if panel.get("title") != "Queue and delivery backlog":
                continue
            backlog_panels += 1
            targets = panel.get("targets", [])
            if len(targets) != 1:
                fail(f"backlog panel must contain one target: {path}")
            target = targets[0]
            expression = str(target.get("expr", ""))
            for source in ("outbox", "inbox", "queue"):
                fragment = f'"backlog_source", "{source}", "service", ".*"'
                if fragment not in expression:
                    fail(f"backlog panel loses {source} source identity: {path}")
            if expression.count("label_replace(") != 3:
                fail(f"backlog panel must retain all three metrics: {path}")
            if target.get("legendFormat") != "{{service}} / {{backlog_source}}":
                fail(f"backlog source is not visible in the panel legend: {path}")
    if backlog_panels == 0:
        fail("no hardened generated backlog panels were found")


def validate_final_artifacts() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_codestra_observability.py")],
        cwd=ROOT,
        check=True,
    )
    with tempfile.TemporaryDirectory(prefix="codestra-grafana-final-") as temporary:
        output_root = Path(temporary)
        (output_root / "codestra").mkdir(parents=True)
        shutil.copytree(GENERATED, output_root / "codestra" / "dashboards")
        shutil.copytree(PROVISIONING, output_root / "codestra" / "provisioning")
        subprocess.run(
            [sys.executable, str(HARDENER), "--root", str(output_root)],
            cwd=ROOT,
            check=True,
        )
        validate_provisioning_tree(output_root)
        validate_hardened_generated_dashboards(output_root)


def main() -> int:
    validate_image_contract()
    validate_packaged_dashboard_pipeline()
    validate_final_artifacts()
    print("CODESTRA_GRAFANA_PRODUCTION_REVIEW=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
