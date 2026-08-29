# Codestra Corporate Grafana Presentation

## Corporate objective

`graf.codestra.media` is the primary operational observability portal for Codestra and the businesses it operates. The landing experience must present the portfolio as one managed enterprise while preserving business, environment and security boundaries.

## Corporate landing dashboard

The home experience should show:

- overall platform availability;
- active critical/high incidents;
- business health scorecards;
- SLO/error-budget status;
- public endpoint/TLS health;
- API error/latency summary;
- queue/backlog summary;
- database/cache saturation summary;
- deployment/config changes in the selected time window;
- security/authentication events;
- provider/dependency health.

## Managed business portfolio

Corporate navigation must include Codestra, MoneyBee, Beyvra Trading, Breero, LARIM-A, Transportation/Freight, Booked4Seasons, Codestra Social, Klyrow Email, Telnexa SMS, Kyqra, Restaurant and Codestra Provisioning. Shared platform services are represented separately as platform dependencies.

Each business view should provide:

1. availability and SLO status;
2. frontend/backend/service health;
3. errors and latency;
4. dependency/provider state;
5. database/cache/queue health where applicable;
6. security/authentication signals;
7. active alerts;
8. recent deployments/config changes;
9. links from metrics to traces and logs;
10. safe incident/customer impact evidence where authorized.

## Persona views

- Executive: health, incident count, SLO attainment, business impact and trend summary.
- SRE/Platform: infrastructure, capacity, dependencies, deployments, alerts and deep diagnostics.
- Security: authentication failures, authorization denials, secret/audit events and suspicious operational signals.
- Business operator: business-specific health and SLA views without infrastructure-admin authority.
- Viewer: read-only safe dashboards.

## Incident question

Every incident flow is designed to answer: **What is broken, where, since when, which business/customer is affected, and what changed?**

Prometheus supplies metrics and SLO state; Alertmanager supplies active/resolved alert state; Loki supplies structured log evidence; Tempo supplies traces; deployment/config telemetry supplies change context.

## Beyvra trading safety

Beyvra dashboards are operational views only. Grafana must not receive broker/exchange signing secrets, execute orders, authorize trades, mutate positions, or become an authoritative balance/execution ledger. Trading health may include safe aggregate latency, provider health, reconciliation state, errors, market-data freshness and capability state.

## Corporate design principles

- consistent folder naming and dashboard titles;
- Codestra business/service/environment variables on every relevant dashboard;
- clean summary-first layout with drill-down links;
- no secret-bearing panels or datasource configuration in dashboard JSON;
- no customer PII in dashboard labels;
- Git-managed provisioning and reviewable changes;
- Viewer by default, explicit Editor/Admin separation;
- Keycloak SSO as the identity boundary.
