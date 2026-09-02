#!/usr/bin/env python3
"""Validate the isolated Grafana staging runtime and minimum dashboard."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml

from deploy_staging_runtime import (
    PreflightError,
    validate_deployment_identity,
    validate_protected_checkout,
    validate_secret_content,
)


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "codestra" / "deploy" / "staging"
COMPOSE = STAGING / "compose.yaml"
DATASOURCE = STAGING / "provisioning" / "datasources" / "prometheus.yml"
DASHBOARD = STAGING / "dashboards" / "middleware-safety-observability.json"
IMAGE = (
    "grafana/grafana:13.2.0@sha256:"
    "3fd54ae1214669f8355f065ec9f6445d5279a3d77095ab048ca045685272429b"
)
REQUIRED_PANELS = {
    "Middleware health",
    "Request rate",
    "4xx / 5xx",
    "Latency p95",
    "Container restart count",
    "Prometheus target health",
    "Provider-canary readiness",
}
REQUIRED_QUERY_FRAGMENTS = {
    "up{job=\"middleware-intake-staging\"}",
    "codestra_http_requests_total",
    "status=~\"4..\"",
    "status=~\"5..\"",
    "codestra_http_request_duration_seconds_bucket",
    "changes(codestra_start_time_seconds",
    "up{job=~\"prometheus-staging|middleware-intake-staging\"}",
    "codestra_operations_dashboard_canary_state",
}


def main() -> None:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert document["name"] == "codestra-grafana-staging"
    assert set(document["services"]) == {"grafana"}
    service = document["services"]["grafana"]
    assert service["image"] == IMAGE
    assert service["container_name"] == "codestra-grafana-staging"
    assert service["init"] is True
    assert service["user"] == "472:0"
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert service.get("privileged") in {None, False}
    assert "ports" not in service
    assert service["expose"] == ["3000"]
    assert "volumes" not in document
    assert not any(
        "grafana_staging_data" in str(mount)
        for mount in service.get("volumes", [])
    )
    assert any(
        str(mount).startswith("/var/lib/grafana:")
        for mount in service["tmpfs"]
    )
    assert set(service["networks"]) == {"codestra_observability"}
    assert document["networks"] == {
        "codestra_observability": {
            "external": True,
            "name": "codestra-observability",
        }
    }
    assert service["secrets"] == [
        {
            "source": "grafana_admin_password",
            "target": "grafana_admin_password",
            "mode": 0o400,
        },
        {
            "source": "grafana_secret_key",
            "target": "grafana_secret_key",
            "mode": 0o400,
        },
    ]
    assert service["environment"]["GF_SECURITY_ADMIN_PASSWORD__FILE"] == (
        "/run/secrets/grafana_admin_password"
    )
    assert service["environment"]["GF_SECURITY_SECRET_KEY__FILE"] == (
        "/run/secrets/grafana_secret_key"
    )
    assert service["environment"]["GF_SERVER_ROOT_URL"] == (
        "${GRAFANA_ROOT_URL:?approved browser-reachable Grafana root URL is required}"
    )
    assert service["environment"]["GF_SERVER_DOMAIN"] == "graf.codestra.media"
    assert service["environment"]["GF_SERVER_ENFORCE_DOMAIN"] == "true"
    assert service["environment"]["GF_SECURITY_COOKIE_SECURE"] == "true"
    assert service["labels"]["com.codestra.source.sha"] == (
        "${GRAFANA_SOURCE_SHA:?exact merged source SHA is required}"
    )
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", IMAGE.rsplit("@", 1)[1])
    serialized_compose = COMPOSE.read_text(encoding="utf-8").lower()
    for forbidden in (
        "privileged: true",
        "seccomp=unconfined",
        "/var/run/docker.sock",
        "klyrow",
        "postal",
    ):
        assert forbidden not in serialized_compose
    deployer = (ROOT / "scripts" / "deploy_staging_runtime.py").read_text(
        encoding="utf-8"
    )
    for required in (
        'SHA40 = re.compile(r"^[0-9a-f]{40}$")',
        'git_output("rev-parse", "HEAD") != source_sha',
        'CANONICAL_REPOSITORY = "https://github.com/appolon1908-hue/Codestra-Grafana-.git"',
        'CANONICAL_MAIN_REF = "refs/remotes/codestra-canonical/main"',
        'f"+refs/heads/main:{CANONICAL_MAIN_REF}"',
        '"merge-base",',
        "validate_protected_checkout()",
        '"--force-recreate"',
        '"--wait-timeout"',
        '"grafana"',
    ):
        assert required in deployer
    validate_secret_content(b"A" * 32, "test secret")
    for malformed in (b"\n" * 32, b"A" * 31, b"A" * 32 + b"\r\n"):
        try:
            validate_secret_content(malformed, "test secret")
        except PreflightError:
            pass
        else:
            raise AssertionError("malformed effective secret was accepted")
    with patch("deploy_staging_runtime.os.geteuid", return_value=1000):
        try:
            validate_deployment_identity()
        except PreflightError:
            pass
        else:
            raise AssertionError("non-root deployment authority was accepted")
    with patch("deploy_staging_runtime.os.geteuid", return_value=0):
        validate_deployment_identity()
    with tempfile.TemporaryDirectory() as temporary:
        protected = Path(temporary) / "authority"
        (protected / ".git").mkdir(parents=True)
        (protected / "scripts").mkdir()
        (protected / "scripts" / "deploy_staging_runtime.py").write_text("# test\n")
        runtime = protected / "codestra" / "deploy" / "staging"
        runtime.mkdir(parents=True)
        (runtime / "compose.yaml").write_text("services: {}\n")
        validate_protected_checkout(
            protected,
            required_uid=protected.stat().st_uid,
            ancestry_root=Path(temporary),
        )
        (runtime / "compose.yaml").chmod(0o666)
        try:
            validate_protected_checkout(
                protected,
                required_uid=protected.stat().st_uid,
                ancestry_root=Path(temporary),
            )
        except PreflightError:
            pass
        else:
            raise AssertionError("writable deployment source was accepted")
        (runtime / "compose.yaml").chmod(0o644)
        (runtime / "escape").symlink_to("/tmp")
        try:
            validate_protected_checkout(
                protected,
                required_uid=protected.stat().st_uid,
                ancestry_root=Path(temporary),
            )
        except PreflightError:
            pass
        else:
            raise AssertionError("symlinked deployment source was accepted")
    assert "root_url = https://graf.codestra.media/" in (
        STAGING / "grafana.ini"
    ).read_text(encoding="utf-8")

    datasource = yaml.safe_load(DATASOURCE.read_text(encoding="utf-8"))
    assert datasource["datasources"] == [
        {
            "name": "Codestra Prometheus",
            "uid": "codestra-prometheus",
            "type": "prometheus",
            "access": "proxy",
            "url": "http://prometheus-staging:9090",
            "isDefault": True,
            "editable": False,
            "jsonData": {
                "httpMethod": "POST",
                "timeInterval": "15s",
                "queryTimeout": "60s",
                "manageAlerts": False,
            },
        }
    ]

    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    assert dashboard["uid"] == "middleware-safety-observability"
    assert dashboard["editable"] is False
    assert dashboard["schemaVersion"] >= 41
    assert {panel["title"] for panel in dashboard["panels"]} == REQUIRED_PANELS
    assert all(
        panel["datasource"]["uid"] == "codestra-prometheus"
        for panel in dashboard["panels"]
    )
    queries = "\n".join(
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel["targets"]
    )
    assert all(fragment in queries for fragment in REQUIRED_QUERY_FRAGMENTS)
    print("GRAFANA_STAGING_RUNTIME_SOURCE=PASS")
    print("GRAFANA_PROMETHEUS_DATASOURCE_SOURCE=PASS")
    print("GRAFANA_DASHBOARD_SOURCE=PASS")


if __name__ == "__main__":
    main()
