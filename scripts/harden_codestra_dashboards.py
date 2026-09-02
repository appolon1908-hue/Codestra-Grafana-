#!/usr/bin/env python3
"""Harden final Codestra dashboard artifacts before validation or packaging.

The source dashboard generator remains deterministic. This finalization step applies
production-only safety corrections to the generated tree and to source-controlled
intake dashboards before either tree is copied into the Grafana image.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


BACKLOG_TITLE = "Queue and delivery backlog"
ODOO_SUCCESS_TITLE = "Odoo delivery success"
BACKLOG_METRICS = (
    ("codestra:outbox_backlog:max", "outbox"),
    ("codestra:inbox_backlog:max", "inbox"),
    ("codestra:queue_depth:max", "queue"),
)
ODOO_SUCCESS_THRESHOLDS = [
    {"color": "red", "value": None},
    {"color": "orange", "value": 95},
    {"color": "green", "value": 99},
]


def fail(message: str) -> None:
    raise SystemExit(f"DASHBOARD_HARDENING_ERROR={message}")


def load_dashboard(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot parse {path}: {exc}")
    if not isinstance(value, dict):
        fail(f"dashboard must be a JSON object: {path}")
    return value


def write_dashboard(path: Path, dashboard: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(dashboard, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def backlog_expression(selector: str) -> str:
    expressions = []
    for metric, source in BACKLOG_METRICS:
        expressions.append(
            "label_replace("
            f"max by (service) ({metric}{{{selector}}}), "
            f'"backlog_source", "{source}", "service", ".*"'
            ")"
        )
    return " or ".join(expressions)


def harden_generated_dashboards(root: Path) -> int:
    dashboards_root = root / "codestra" / "dashboards"
    if not dashboards_root.is_dir():
        fail(f"generated dashboard directory is missing: {dashboards_root}")

    hardened = 0
    selector_pattern = re.compile(r"codestra:outbox_backlog:max\{([^}]*)\}")
    for path in sorted(dashboards_root.rglob("*.json")):
        dashboard = load_dashboard(path)
        changed = False
        for panel in dashboard.get("panels", []):
            if not isinstance(panel, dict) or panel.get("title") != BACKLOG_TITLE:
                continue
            targets = panel.get("targets")
            if not isinstance(targets, list) or len(targets) != 1:
                fail(f"backlog panel must contain one target: {path}")
            target = targets[0]
            if not isinstance(target, dict):
                fail(f"backlog target must be an object: {path}")
            original = str(target.get("expr", ""))
            match = selector_pattern.search(original)
            if match is None:
                fail(f"backlog selector cannot be derived: {path}")
            target["expr"] = backlog_expression(match.group(1))
            target["legendFormat"] = "{{service}} / {{backlog_source}}"
            changed = True
            hardened += 1
        if changed:
            write_dashboard(path, dashboard)

    if hardened == 0:
        fail("no generated backlog panels were found")
    return hardened


def harden_intake_dashboards(root: Path) -> int:
    dashboards_root = root / "codestra" / "provisioning" / "intake-dashboards"
    files = sorted(dashboards_root.rglob("*.json")) if dashboards_root.is_dir() else []
    if not files:
        fail("no intake dashboards were found")

    hardened = 0
    for path in files:
        dashboard = load_dashboard(path)
        changed = False
        for panel in dashboard.get("panels", []):
            if not isinstance(panel, dict) or panel.get("title") != ODOO_SUCCESS_TITLE:
                continue
            defaults = panel.setdefault("fieldConfig", {}).setdefault("defaults", {})
            defaults["thresholds"] = {
                "mode": "absolute",
                "steps": ODOO_SUCCESS_THRESHOLDS,
            }
            changed = True
            hardened += 1
        if changed:
            write_dashboard(path, dashboard)

    if hardened != 1:
        fail(f"expected exactly one Odoo success panel, found {hardened}")
    return hardened


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository-shaped root containing codestra/dashboards and provisioning.",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    backlog_count = harden_generated_dashboards(root)
    intake_count = harden_intake_dashboards(root)
    print(f"HARDENED_BACKLOG_PANELS={backlog_count}")
    print(f"HARDENED_INTAKE_SUCCESS_PANELS={intake_count}")
    print("CODESTRA_DASHBOARD_HARDENING=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
