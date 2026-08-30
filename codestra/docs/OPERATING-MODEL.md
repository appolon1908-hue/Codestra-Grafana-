# Codestra Grafana Operating Model

## Mission

`graf.codestra.media` is the human operational observability portal for Codestra. It correlates Prometheus metrics, Loki logs, Tempo traces and Alertmanager state, authenticates through Codestra Keycloak, and presents every managed business through one consistent corporate operating model.

The portal is designed to answer:

> What is broken or degraded, where, since when, which Codestra business is affected, what is the safe aggregate impact, who owns it, and what changed?

Grafana is presentation and investigation authority only. Superset remains the business-intelligence application. Product runtimes, Odoo, Middleware, n8n, providers and financial systems remain authoritative for business actions.

## Network and integration model

Human access terminates at the approved edge URL:

- Grafana public URL: `https://graf.codestra.media/`
- Keycloak issuer: `https://auth.codestra.co/realms/codestra`

Grafana reaches observability backends through private service endpoints:

- Prometheus: `http://prometheus:9090`
- Loki query endpoint: `http://loki-query:3100`
- Tempo: `http://tempo:3200`
- Alertmanager: `http://alertmanager:9093`

The native Grafana container port binds only to `127.0.0.1` on the host. Datasource egress is allowlisted to the four private endpoints. DNS existence never authorizes public access to Grafana backends, exporters, Alloy, OpenTelemetry or OpenBao.

## Source-controlled authority

- `codestra/config/grafana.ini` — production mode, external PostgreSQL, encrypted state, Keycloak OAuth, security headers and authority boundaries.
- `codestra/provisioning/datasources/codestra.yml` — immutable private datasources and metrics/logs/traces correlation.
- `codestra/provisioning/dashboards/codestra.yml` — immutable folder provisioning.
- `codestra/business-registry.json` — approved Codestra business, application and platform-service catalogue.
- `codestra/rbac-policy.json` — role, team, folder and data-isolation policy.
- `codestra/runtime.v1.json` — non-deployed runtime and activation contract.
- `codestra/deploy/Dockerfile` — deterministic dashboard generation and immutable Grafana overlay image.
- `codestra/deploy/compose.candidate.yaml` — hardened loopback-only runtime candidate.
- `scripts/generate_codestra_dashboards.py` — deterministic corporate dashboard generator.
- `scripts/validate_codestra_observability.py` — fail-closed portfolio, SSO, datasource, RBAC, dashboard, packaging and runtime validation.

Generated dashboard JSON is build output. The source of truth is the generator plus the business registry; this prevents checked-in dashboards from silently drifting away from the canonical metric contract.

## Corporate dashboard folders

Provisioned folders are:

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

The image build creates an executive dashboard, incident triage, fifteen platform/specialist dashboards, one health dashboard for each managed business, and one dashboard for every registered application service.

## Identity and RBAC

Keycloak Generic OAuth uses Authorization Code + PKCE and refresh-token rotation. Local login, basic authentication, auth proxy, anonymous access and initial local-admin creation are disabled.

Approved realm roles are:

- `observability-viewer` → Viewer
- `observability-operator` → Editor
- `observability-admin` → GrafanaAdmin

Unmapped users are rejected by strict role mapping. Business teams default to Viewer. Provisioned dashboards are read-only.

Grafana OSS external team synchronization is not assumed. Folder permission is not datasource isolation. A business-specific non-corporate access claim requires all of the following evidence:

1. approved Keycloak team membership or a separately controlled Grafana organization;
2. business-aware datasource tenant enforcement;
3. cross-business allow/deny tests;
4. audited folder and datasource permissions;
5. removal and emergency-access procedures.

Until those gates pass, the corporate organization displays aggregate operational telemetry only.

## Data and authority safety

- Grafana-managed alerting is disabled; Prometheus and Alertmanager retain alert authority.
- Public dashboards, snapshots, anonymous access and SMTP are disabled.
- Dashboards contain no mutation buttons or external action links.
- No provider, database, OIDC, broker, exchange or API credentials are stored in provisioning or dashboard JSON.
- Customer and person identifiers are forbidden as Prometheus or Loki stream labels.
- The default corporate organization does not claim customer-level data authority.
- Grafana never sends email/SMS/voice, runs n8n, writes Odoo, enables a provider, funds a loan, or places/cancels/replaces a trade.
- Beyvra views contain only safe aggregate operational health and never trading credentials or authoritative balances/positions/executions.

## State, secrets and recovery

Grafana uses external PostgreSQL with TLS `verify-full`; database user, password and CA are runtime secret files. A separate high-entropy secret key encrypts Grafana-held sensitive state. The OIDC client secret is also file-injected.

Production evidence must prove:

- least-privilege database role and network path;
- encrypted database storage and backup;
- successful database restore to an isolated environment;
- persistence of users, teams, folders and dashboard state after restart;
- secret rotation for OIDC, database and Grafana encryption key;
- immutable image digest and upstream source provenance;
- private datasource connectivity and denial of unapproved egress;
- Keycloak login, logout, role mapping and role-removal behavior;
- cross-business denial behavior before business-scoped access is released.

## Packaging and validation

The source gate is:

```bash
python3 -m pip install PyYAML==6.0.3
python3 scripts/validate_codestra_observability.py
docker compose -f codestra/deploy/compose.candidate.yaml config
```

CI compiles the generator and validator, regenerates the complete dashboard portfolio, validates corporate metric/log query names, checks SSO/RBAC/datasource safety, and renders the hardened runtime candidate with immutable placeholder references.

## Promotion and activation

Promotion order is:

`feature/* -> development -> test -> staging -> production -> main`

Merge or CI success does not deploy Grafana. Production remains blocked until every `codestra/runtime.v1.json` activation gate has evidence and is changed through a reviewed release-authority update. This PR deliberately leaves all activation gates false.
