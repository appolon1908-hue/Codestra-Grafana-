#!/usr/bin/env python3
from __future__ import annotations

import configparser
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "config" / "codestra" / "runtime.v1.json"
INI = ROOT / "config" / "codestra" / "grafana.ini.example"


def fail(message: str) -> None:
    print(f"GRAFANA_CODESTRA_VALIDATION_ERROR={message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    data = json.loads(RUNTIME.read_text(encoding="utf-8"))
    if data.get("hostname") != "graf.codestra.media":
        fail("canonical hostname mismatch")
    if data.get("hostBind") != "127.0.0.1:3000":
        fail("host port must bind to loopback")
    if data.get("publicNativePortAllowed") is not False:
        fail("native Grafana port must not be public")

    oidc = data.get("oidc", {})
    if oidc.get("issuer") != "https://auth.codestra.co/realms/codestra":
        fail("issuer mismatch")
    if oidc.get("clientId") != "grafana-observability":
        fail("client ID mismatch")
    if oidc.get("callback") != "https://graf.codestra.media/login/generic_oauth":
        fail("callback mismatch")
    if oidc.get("pkce") != "S256":
        fail("PKCE S256 is required")

    if any(value is True for value in data.get("activation", {}).values()):
        fail("source branch must not activate deployment")

    parser = configparser.ConfigParser(interpolation=None)
    parser.read(INI, encoding="utf-8")
    if parser.get("server", "root_url") != "https://graf.codestra.media/":
        fail("Grafana root URL mismatch")
    if parser.getboolean("auth.generic_oauth", "enabled") is not True:
        fail("generic OAuth must be enabled")
    if parser.get("auth.generic_oauth", "client_id") != "grafana-observability":
        fail("Grafana client ID mismatch")
    if parser.getboolean("auth.generic_oauth", "use_pkce") is not True:
        fail("Grafana PKCE must be enabled")
    secret = parser.get("auth.generic_oauth", "client_secret")
    if secret != "$__file{/run/secrets/grafana_oidc_client_secret}":
        fail("Grafana secret must come from the approved file path")
    if parser.getboolean("auth.anonymous", "enabled") is not False:
        fail("anonymous access must be disabled")

    print("GRAFANA_CODESTRA_INTEGRATION_VALID=1")


if __name__ == "__main__":
    main()
