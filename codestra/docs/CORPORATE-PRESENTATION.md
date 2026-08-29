# Codestra Corporate Grafana Presentation

## Corporate objective

`graf.codestra.media` is the primary operational observability portal for Codestra and the businesses it manages. The experience presents the portfolio as one professionally operated enterprise while preserving business, environment, security, financial and data-access boundaries.

Grafana answers operational questions; it does not replace Superset business intelligence, Odoo workflow, product administration, customer support systems, provider consoles or financial ledgers.

## Corporate landing dashboard

The default executive experience shows:

- total platform and business-service availability;
- firing critical, high and warning incidents;
- health by managed business;
- SLO/error-budget burn status;
- public endpoint, DNS and TLS health from approved probes;
- API traffic, error and p95 latency summaries;
- queue, worker, inbox and outbox health;
- database, cache, host and container saturation signals;
- deployment, configuration and capability changes in the selected time window;
- authentication, authorization, reconciliation and security signals;
- provider and dependency health.

Every page starts with a summary and then offers drill-down to metrics, redacted logs and traces. No page includes a business-mutation control.

## Managed business portfolio

Corporate navigation represents:

1. Codestra
2. MoneyBee
3. Beyvra Trading
4. Breero
5. LARIM-A
6. Transportation and Freight
7. Booked4Seasons
8. Codestra Social
9. Klyrow Email
10. Telnexa Messaging
11. Kyqra
12. Restaurant Platform
13. Codestra Provisioning

Shared platform dependencies are presented separately under the `platform` business scope.

Each business view provides:

- availability and SLO state;
- frontend/backend/service health;
- traffic, error and latency trends;
- dependency and provider state;
- database/cache/queue health when applicable;
- security and authentication signals;
- firing alert state;
- current deployment/version evidence;
- recent deployment, configuration and capability changes;
- metric-to-trace and trace-to-redacted-log correlation;
- safe aggregate impact indicators.

The corporate portal does not claim customer-level data access. Any separately approved restricted investigation path requires its own data controls, access evidence and auditing.

## Persona views

### Executive viewer

Read-only health, incident count, SLO/error-budget state, aggregate business impact and trend summaries. No raw infrastructure secrets, payloads or business controls.

### SRE and platform operator

Operational dashboards, Explore, infrastructure/capacity analysis, dependency correlation and source-controlled dashboard improvement. Business-system mutations and provider writes remain outside Grafana.

### Security operator

Authentication failure, authorization denial, protected audit, capability-state and suspicious operational signals. Access to sensitive log streams requires separate approval and is not inferred from a Grafana folder role.

### Business viewer

Read-only aggregate health for the approved business. Folder permission alone does not prove datasource isolation; business-specific access is released only after Keycloak team mapping, tenant-aware datasources and cross-business denial tests are evidenced.

### Grafana administrator

Platform administration through the approved `observability-admin` realm role. This role does not grant OpenBao, product-admin, communications, lending, trading or infrastructure-shell authority.

## Incident question

Every incident flow is designed to answer:

> **What is broken, where, since when, which Codestra business is affected, what is the safe aggregate impact, who owns it, and what changed?**

Prometheus supplies metrics and SLO state; Alertmanager supplies firing/resolved incident state; Loki supplies redacted structured log evidence; Tempo supplies traces; deployment/configuration telemetry supplies change context.

## Beyvra financial and trading safety

Beyvra dashboards are operational views only. Grafana never receives broker/exchange signing secrets, executes orders, authorizes trades, mutates positions, or becomes an authoritative balance/execution ledger. Trading health may include aggregate latency, provider health, reconciliation state, errors, market-data freshness and externally effective capability state.

## Corporate design principles

- Codestra ownership is visible in titles, navigation and descriptions.
- Business, application, service, environment, region and deployment selectors are consistent.
- Summary-first layouts use clear operational language and bounded time windows.
- Provisioned dashboards and datasources are immutable and source-controlled.
- Viewer is the default; operator and administrator authority are explicit.
- Keycloak Authorization Code + PKCE is the human identity boundary.
- Metrics, logs and traces use internal datasource endpoints only.
- No customer PII, credentials, raw payloads or high-cardinality identifiers appear as labels.
- No direct email, SMS, voice, Odoo, n8n, provider or trading action exists in a dashboard.
- Grafana-managed alerting, public dashboards, anonymous access, SMTP and local login are disabled.
