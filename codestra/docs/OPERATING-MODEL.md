# Codestra Grafana Operating Model

## Mission

`graf.codestra.media` is the operational observability portal for Codestra. It correlates Prometheus metrics, Loki logs, Tempo traces, and Alertmanager state while using Keycloak for human authentication.

The control plane is designed to answer:

> What is broken, where, since when, which business/customer is affected, and what changed?

## Canonical integrations

- Grafana: `https://graf.codestra.media`
- Prometheus: `https://prom.codestra.media`
- Loki: `https://loki.codestra.media`
- Tempo: `https://temp.codestra.media`
- Alertmanager: `https://aler.codestra.media`
- Keycloak issuer family: `https://auth.codestra.co/realms/codestra`

The monitoring DNS names may resolve to `37.27.128.39`, but Prometheus, Loki, Tempo, Alertmanager, exporters, Alloy, OpenTelemetry, and OpenBao remain private/restricted services. DNS is not authorization.

## Source-controlled configuration

- `codestra/config/grafana.ini` — canonical hostname and Keycloak OAuth configuration. OAuth client secret is file-injected at runtime and must not be committed.
- `codestra/provisioning/datasources/codestra.yml` — immutable datasource definitions and metrics/logs/traces correlation.
- `codestra/provisioning/dashboards/codestra.yml` — immutable folder/dashboard provisioning.
- `codestra/business-registry.json` — business, application repository, and canonical service registry.
- `codestra/rbac-policy.json` — Viewer/Admin/Editor and team ownership policy.
- `scripts/generate_codestra_dashboards.py` — deterministic dashboard generation for every registered application plus platform dashboards.
- `scripts/validate_codestra_observability.py` — fail-closed source validation.

## Dashboard folders

Provisioned folders cover:

- Executive
- Incident Triage
- Platform
- Business and Applications
- Environment
- Server
- Database
- API
- Security
- Contact Center and Campaigns
- Deployment and Version
- SLO and Error Budget

The generator creates a dashboard for every business and every registered frontend/backend/full-stack application in `business-registry.json`.

## Identity and RBAC

Keycloak Generic OAuth uses Authorization Code + PKCE. Normal users default to Grafana Viewer. `grafana-editor` maps to Editor and `grafana-admin` maps to Admin. Grafana server-admin privilege is not delegated through OAuth.

Grafana OSS teams are used for ownership/editing. This repository does not assume paid external Team Sync. Team membership can be managed through Grafana administration/API while Keycloak remains the authentication and coarse role authority.

## Data safety

- Grafana is read-only observability authority, not a business write authority.
- Dashboards must not contain action buttons that mutate business state.
- No provider/API/broker/database secrets belong in dashboard JSON or datasource files.
- Tenant/customer IDs may appear as protected structured log/trace fields when required for incident analysis, but never as Prometheus labels or Loki stream labels.
- Beyvra trading dashboards never receive trade-signing credentials and never place/cancel/replace trades.

## Packaging gate

Before packaging/deploying the Codestra Grafana layer, run:

```bash
python3 scripts/generate_codestra_dashboards.py
python3 scripts/validate_codestra_observability.py
```

The generated `codestra/dashboards/` directory is the input for Grafana file provisioning. Deployment is a separate controlled operation; merging these source files does not deploy or expose any service.

## Remaining external dependencies

This repository prepares Grafana to consume telemetry. Each runtime still must implement the telemetry contract and Prometheus must attach the canonical `codestra_business`, `service`, and `environment` labels. Alloy/OpenTelemetry must deliver structured logs/traces, and deployment pipelines must emit deployment/configuration change events so Grafana can correlate incidents with changes.
