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

The isolated deployment authority for the Middleware safety mission is
`codestra/deploy/staging/compose.yaml`. It consumes the immutable official
Grafana image, publishes no host port, joins only `codestra-observability`, and
provisions one read-only Prometheus datasource plus the minimum staging safety
dashboard. It is separate from the production PostgreSQL/OIDC candidate.

Rendering or deployment must use `scripts/deploy_staging_runtime.py`.
Deployment mode rejects a dirty checkout, a non-SHA label, a SHA other than the
checked-out head, and a head not merged into `origin/main`; it then recreates
only the Grafana service. Never invoke that Python file as root from a
user-owned or user-writable checkout. First fetch the accepted exact main SHA
into a standalone checkout below a root-owned, non-group-writable,
non-other-writable directory. The deployment preflight recursively enforces
that protection for the Git metadata, entrypoint, Compose file, dashboards,
and provisioning source before Docker is invoked; Git worktrees and symlinks
in that execution closure are rejected. Deployment mode must run as root: the
preflight reads and validates the UID-472-owned `0400`/`0600` secret files
without broadening their ownership or permissions. Render mode remains
available to an unprivileged review account and never reads secret content.

A root operator must prepare the protected source before running any repository
code:

```bash
install -d -o root -g root -m 0755 /opt/codestra-observability
install -d -o root -g root -m 0700 /opt/codestra-observability/grafana-authority
git -C /opt/codestra-observability/grafana-authority init
git -C /opt/codestra-observability/grafana-authority remote add origin https://github.com/appolon1908-hue/Codestra-Grafana-.git
git -C /opt/codestra-observability/grafana-authority fetch --no-tags origin refs/heads/main
git -C /opt/codestra-observability/grafana-authority checkout --detach <accepted-main-sha>
chown -R root:root /opt/codestra-observability/grafana-authority
chmod -R go-w /opt/codestra-observability/grafana-authority
/usr/bin/python3 -I /opt/codestra-observability/grafana-authority/scripts/deploy_staging_runtime.py ...
```

The mandatory `-I` interpreter mode removes the checkout and caller working
directory from Python's import path before the entrypoint starts. Deployment
preflight also rejects a writable `scripts/` parent directory, so the
entrypoint cannot be replaced or shadow standard-library imports before its
recursive source checks run. Privileged Git and Docker subprocesses use their
fixed root-owned system paths. Git receives only a sanitized environment with
global/system configuration disabled, and Compose is invoked through the
system plugin directly with no inherited `HOME`, `DOCKER_CONFIG`, or
executable search path.

This isolated dashboard runtime is intentionally stateless: its SQLite data
directory is a private tmpfs and all dashboards and datasources are
source-provisioned. Recreating the service therefore reapplies the protected
admin credential instead of retaining an obsolete database-backed password.
Deployment waits up to 120 seconds for the source-defined healthcheck.
The deployment requires the canonical browser root
`https://graf.codestra.media/`; redirects and generated links never expose the
Docker-internal service name.

## Safety

Never commit datasource credentials, API tokens, passwords, private URLs carrying secrets, certificates, customer message content, recordings or PII.
