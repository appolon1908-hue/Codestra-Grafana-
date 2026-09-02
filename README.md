# Codestra Grafana

Principal repository for Codestra Grafana OSS dashboards, datasource provisioning templates, dashboard provisioning, folders, alert visualization, operational views, release evidence, validation and runbooks.

## Authority boundary

This repository owns Grafana-specific source only. It does not own Prometheus scrape configuration, Alertmanager routing, Loki storage/configuration, Tempo tracing backend configuration, OpenTelemetry Collector configuration, or business-system runtime source.

Shared observability topology and environment composition are coordinated through `appolon1908-hue/Infustruction-repo`. Communications dashboard information architecture is coordinated through `appolon1908-hue/communication-platform-`.

## Data path

```text
Applications / infrastructure
  -> metrics/logs/traces
  -> Prometheus / Loki / Tempo
  -> Grafana
```

Grafana is an operational visualization layer. Controlled business mutations must never be executed directly from Grafana into Postal, Jasmin, VICIdial, Odoo, databases, or provider APIs.

## Required dashboard families

- Executive operational overview
- Caddy/Kong/Keycloak edge and identity
- Middleware command/inbox/outbox/reconciliation health
- Klyrow/email deliverability and queue health
- Telnexa/SMS delivery and provider health
- VICIdial/voice queue and call health
- PostgreSQL/Redis/NATS/container/host health
- Webhooks, dead letters, retries and reconciliation
- SLO/error-budget views

## Branch model

After bootstrap use `feature/* -> development -> staging -> main` with documentation/fix branches as needed. Production deployment must consume an accepted immutable source identity; merge alone does not authorize deployment.

## Safety

Never commit datasource credentials, API tokens, passwords, private URLs carrying secrets, certificates, customer message content, recordings or PII.
