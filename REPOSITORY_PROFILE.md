# Repository Profile — `Codestra-Grafana-`

## Identity

- **Repository:** `appolon1908-hue/Codestra-Grafana-`
- **Category:** Observability UI — Grafana
- **Visibility:** `public`
- **Default branch:** `main`
- **Canonical hostname:** `graf.codestra.media`
- **Exposure:** Browser-facing only through authenticated Caddy routing
- **Authority:** Primary Grafana configuration, dashboard, datasource, folder, and operational alert-view authority

## Purpose

Provides operational dashboards and exploration for metrics, logs, and traces across Codestra-managed businesses and platform services.

## Owns

- Provisioned Grafana datasources, folders, dashboards, alert views, and role mappings
- Operational visualization for Prometheus, Loki, Tempo, exporters, services, SLOs, reconciliation, and infrastructure
- Grafana runtime configuration and private-listener deployment source

## Does not own

- Metrics, logs, or traces as systems of record
- Product/operator mutations that require governed APIs
- Anonymous or unauthenticated public monitoring access

## Key integrations

- Prometheus, Loki, and Tempo on private networks
- Keycloak OIDC client `grafana-observability`
- Caddy authenticated edge route
- Alertmanager and platform runbooks

## Current priorities

1. Provision version-controlled dashboards and datasources
2. Enforce Keycloak role mapping and disable anonymous/local login where approved
3. Add infrastructure, communications, identity, edge, database, and SLO views
4. Prove dashboard imports, datasource health, backup/restore, upgrade, and rollback

## Governance and safety

- Promotion model: `feature/docs/fix/security/upgrade -> development -> test -> staging -> production -> main`.
- Native port `3000` must remain private; public access is only through `graf.codestra.media` and approved authentication.
- Never commit datasource credentials, OIDC secrets, API keys, customer data, or rendered secret values.
- Merge does not deploy Grafana, install secrets, create Keycloak clients, reload Caddy, or expose a port.

## Account-wide catalog

See `appolon1908-hue/documentaions/REPOSITORY_CATALOG.md`.
