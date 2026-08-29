# Codestra Observability Contract

This document is the integration contract required for every runtime that appears in Codestra Grafana.

## Purpose

The Grafana control plane must make it possible to answer, from one incident view:

1. What is broken?
2. Where is it broken (business, service, environment, host/container)?
3. Since when?
4. Which business and, when present in protected event data, which tenant/customer is affected?
5. What deployment/configuration change preceded the failure?

Grafana is observability only. It must not execute business mutations, provider writes, Odoo writes, SMS/email delivery, PSTN dialing, social publishing, or trading orders.

## Required low-cardinality metrics labels

Every scraped runtime target must expose or receive these labels through Prometheus service discovery/relabeling:

- `codestra_managed="true"`
- `codestra_business` — stable business identifier from `codestra/business-registry.json`
- `service` — canonical service name from the registry
- `environment` — `development`, `test`, `staging`, or `production`
- `instance` — host/target identity

Never use `tenant_id`, customer IDs, email addresses, phone numbers, account IDs, order IDs, correlation IDs, request IDs, or trace IDs as Prometheus labels.

## Required application metrics

Backends and collectors should provide the following normalized metrics directly or through recording rules:

- `up`
- `http_server_requests_total{status=...}`
- `codestra_build_info{version,git_sha}` with value `1`
- dependency availability/latency metrics
- queue depth and worker failure metrics where applicable
- outbox/inbox/reconciliation metrics for Middleware-backed integrations
- provider delivery/error metrics for communication services
- authentication/authorization denial counters for identity/gateway services

Frontends must be represented by synthetic availability (Blackbox) plus browser/RUM or OpenTelemetry web telemetry. A browser must never receive infrastructure datasource credentials or provider API secrets.

## Structured logs (Loki)

JSON logs should contain fields where relevant:

- `timestamp`
- `level`
- `codestra_business`
- `service`
- `environment`
- `event`
- `error_code`
- `correlation_id`
- `trace_id`
- `deployment_sha`
- `tenant_id` (field only; never a Loki label)

Secrets, access tokens, passwords, API keys, broker/exchange credentials, card/bank data, and sensitive PII must be redacted before ingestion.

Deployment systems should emit `event="deployment"`, configuration authorities `event="config_change"`, and capability systems `event="feature_flag_change"` so the incident dashboard can answer “what changed?”.

## OpenTelemetry / Tempo

Required resource attributes:

- `service.name`
- `service.version`
- `deployment.environment`
- `codestra.business`
- `codestra.correlation_id` when safe and applicable
- `deployment.sha`

Trace context must propagate across Caddy -> Kong -> Middleware -> owned downstream service. The original application correlation ID should also be preserved.

## Alerts

Prometheus evaluates metrics; Alertmanager groups/routes alerts. Any business-side notification or incident mutation should be handed to Middleware rather than allowing Grafana/Alertmanager to become an independent cross-system write authority.

Every alert should include:

- severity
- business
- service
- environment
- summary
- runbook URL
- dashboard URL
- correlation/trace link when available

## Beyvra trading safety

Beyvra dashboards are strictly read-only operational views. Grafana, Prometheus, Loki, Tempo, Alertmanager, Alloy, and OpenTelemetry must never possess broker/exchange trade-signing credentials and must never expose an action that can place, modify, cancel, or authorize a trade. Production trading secrets belong in OpenBao and are retrieved only by explicitly authorized backend/execution workloads.

## Ownership

`codestra/business-registry.json` is the Grafana-side registry of business/service names. Product repositories remain authoritative for their application code. Prometheus owns scrape/recording rule configuration, Loki log storage, Tempo trace storage, Alertmanager alert routing, Keycloak identity, and OpenBao secrets.
