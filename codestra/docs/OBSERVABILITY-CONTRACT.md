# Codestra Grafana Observability Contract

This is the Grafana-side integration contract for every Codestra-managed application and platform service represented in the corporate operational portal.

## Purpose

The corporate incident view must answer:

1. What is broken or degraded?
2. Which Codestra business, application, service, environment, region and deployment are affected?
3. When did the condition begin and how is it changing?
4. What safe aggregate customer or operational impact is visible?
5. Which deployment, configuration, capability or provider change preceded the condition?
6. Which owner and runbook are responsible for the response?

Grafana is a read-only presentation and investigation authority. It must not execute business mutations, provider writes, Odoo writes, n8n workflows, email/SMS delivery, PSTN dialing, social publishing, lending submissions, funding actions, or trading orders.

## Canonical dimensions

Every Prometheus target and every bounded Loki stream must carry:

- `codestra_business`
- `application`
- `service`
- `environment`
- `server`
- `region`
- `deployment`

`codestra_business="platform"` represents shared corporate infrastructure. Business IDs are defined in `codestra/business-registry.json`.

Customer IDs, end-tenant IDs, account IDs, user IDs, email addresses, phone numbers, message IDs, order IDs, request IDs, correlation IDs, trace IDs, raw URLs, query strings, SQL statements, container IDs, pod UIDs and unbounded exception text are forbidden as Prometheus labels and Loki stream labels.

## Canonical application metrics

Product backends should expose stable metric families that Prometheus normalizes and records into:

- `codestra:http_requests:rate5m`
- `codestra:http_error_ratio:5m`
- `codestra:http_duration_seconds:p50_5m`
- `codestra:http_duration_seconds:p95_5m`
- `codestra:http_duration_seconds:p99_5m`
- `codestra:dependency_latency_seconds:p95_5m`
- `codestra:database_latency_seconds:p95_5m`
- `codestra:queue_depth:max`
- `codestra:worker_failures:rate5m`
- `codestra:outbox_backlog:max`
- `codestra:outbox_oldest_age_seconds:max`
- `codestra:inbox_backlog:max`
- `codestra:inbox_oldest_age_seconds:max`
- `codestra:webhook_delivery_success_ratio:5m`
- `codestra:authentication_failures:rate5m`
- `codestra:authorization_denials:rate5m`
- `codestra:idempotency_conflicts:rate5m`
- `codestra:reconciliation_failures:rate5m`
- `codestra:external_provider_failures:rate5m`
- `codestra:target_up:ratio`
- `codestra:deployment_info:max`
- `codestra:slo_http_error_ratio:*`
- `codestra:slo_http_burn_rate:*`

Frontends are represented through Blackbox synthetic availability plus approved browser/OpenTelemetry web telemetry. Browsers never receive infrastructure datasource credentials, provider credentials or observability write credentials.

## Structured logs and Loki

Logs are JSON and use the canonical bounded stream dimensions. Protected structured fields may include:

- `timestamp`
- `level`
- `event_family`
- `operation`
- `result`
- `error_code`
- `request_id`
- `correlation_id`
- `trace_id`
- `deployment_sha`
- a redacted internal object reference when operationally necessary

Alloy and OpenTelemetry redact before forwarding. Authorization headers, cookies, passwords, API keys, private keys, client secrets, database DSNs, broker/exchange credentials, raw payment/lending/communications payloads and sensitive personal data are forbidden.

Customer-level identifiers may exist only in a separately authorized protected investigation stream when a documented operational need exists. The default corporate Grafana organization and generated dashboards do not claim or provide customer-level data authority.

Deployment systems emit `event_family="deployment"`, configuration authorities emit `event_family="configuration"`, and capability systems emit `event_family="feature_flag"` or `event_family="capability"`. This lets the incident view answer “what changed?” without storing raw deployment secrets or payloads.

## OpenTelemetry and Tempo

Required resource attributes are:

- `service.name`
- `service.namespace`
- `service.version`
- `deployment.environment.name`
- `deployment.id`
- `cloud.region` or approved `codestra.region`
- `codestra.business`
- approved server/host identity

Trace context propagates through the owned request path. Trace and correlation IDs are searchable fields and exemplars, not metric or log-stream labels. Spans must not carry credentials, raw bodies, account/customer identifiers, order IDs or financial signing material as unbounded attributes.

## SLO and incident presentation

Prometheus evaluates metrics and SLO/error-budget rules. Alertmanager groups and routes alert state. Grafana displays and correlates that state but Grafana-managed alerting remains disabled.

Every actionable alert must provide:

- `severity`
- `owner`
- `codestra_business`
- `service`
- `environment`
- summary and description
- HTTPS runbook URL

Region, deployment and dashboard/trace context may be added when present. Direct Grafana receivers, dashboard buttons, or plugins that mutate an incident or business system are not approved.

## Identity and business access

Keycloak authenticates users through Authorization Code + PKCE. Approved realm roles are:

- `observability-viewer` → Viewer
- `observability-operator` → Editor
- `observability-admin` → GrafanaAdmin

Folder permissions are presentation controls, not datasource isolation. Business-specific non-corporate access is not considered isolated until Keycloak team membership, folder permissions, datasource tenant enforcement and cross-business denial tests are all proven. Default business teams remain Viewer.

## Beyvra financial and trading boundary

Beyvra dashboards may show aggregate availability, latency, provider health, reconciliation state, error rate, market-data freshness and capability state. Grafana, Prometheus, Loki, Tempo, Alertmanager, Alloy and OpenTelemetry never possess broker/exchange signing credentials and never expose an action that can place, modify, cancel or authorize a trade. They are not authoritative balance, position, execution or ledger systems.

## Ownership

- Grafana owns source-controlled operational presentation and correlation.
- Prometheus owns metrics, recording rules, SLO evaluation and alert evaluation.
- Loki owns log storage and query.
- Tempo owns trace storage and query.
- Alertmanager owns alert grouping/routing.
- OpenTelemetry and Alloy own governed collection and normalization.
- Keycloak owns human identity.
- OpenBao owns secrets and PKI.
- Product repositories remain authoritative for business behavior and instrumentation.

Merging this contract does not activate a datasource, deploy Grafana, create an OIDC client, apply RBAC, expose a port, or authorize any business mutation.
