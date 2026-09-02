# Codestra Grafana Authority

Principal repository: `appolon1908-hue/Codestra-Grafana-`

Canonical service host: `graf.codestra.media`
Canonical DNS target: `37.27.128.39`

No alternate public service hostname is authoritative for this repository. Configuration, documentation, examples, dashboards, OAuth callback URLs, reverse-proxy references, and smoke tests must use `graf.codestra.media` when a public hostname is required.

## Ownership

This repository owns Grafana OSS configuration, provisioning, dashboards, data-source definitions, plugins, RBAC templates, alert presentation, upgrade validation, and Grafana-specific runbooks.

It does not own Prometheus, Loki, Tempo, OpenTelemetry, Superset, OpenBao, exporters, Caddy, or application runtime configuration.

## Exposure

Browser access is allowed only through authenticated HTTPS ingress. Direct Grafana service ports remain private. The intended edge path is `Internet -> Caddy -> graf.codestra.media -> Grafana` with approved authentication and security headers.

## Integration

Upstream data sources: Prometheus, Loki, Tempo and approved read-only analytics/health sources.
Downstream consumers: authenticated operators and dashboards only.

## Branch policy

Persistent branches: `main`, `development`, `test`, `staging`, `production`.
Temporary work: `feature/*`, `fix/*`, `upgrade/*`, `security/*`, `docs/*`, `hotfix/*`, optional `release/*` and `rollback/*`.

Promotion: work branch -> development -> test -> staging -> production -> main. Never perform an upstream Grafana upgrade directly on protected persistent branches.
