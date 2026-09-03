# Codestra Grafana production readiness

## Current state

```text
REPOSITORY=appolon1908-hue/Codestra-Grafana-
REPOSITORY_ID=1350767762
TARGET_SERVER=37.27.128.39
PUBLIC_HOSTNAME=graf.codestra.media
SOURCE_STATE=PRODUCTION_SOURCE_CANDIDATE
RUNTIME_STATE=NOT_CERTIFIED_NOT_DEPLOYED_BY_THIS_CHANGE
```

This package makes the repository source certifiable and fail-closed. It does not claim that a Grafana image has been published, staged, or deployed. A pull-request merge does not authorize a production restart, datasource mutation, dashboard mutation, DNS change, certificate change, or identity change.

## Canonical boundaries

- Grafana is the browser-facing visualization service.
- Prometheus and PostgreSQL remain private dependencies.
- PostgreSQL Exporter is reachable only as `postgres-exporter:9187` on the approved private monitoring network.
- PostgreSQL Exporter has no public hostname, host port, Caddy route, Kong route, Ingress, Gateway, LoadBalancer, or NodePort.
- Human authentication uses `https://auth.codestra.co/realms/codestra`.
- Datasource secrets remain server-side and file-injected; they never enter dashboards or browser configuration.

## Source certification

The following must pass on the exact pull-request head and protected merge result:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/validate_codestra_observability.py
python3 scripts/validate_production_readiness.py
```

The checks cover repository aliases, private-service authority, decoded generated dashboard content, Grafana configuration, OIDC, datasource provisioning, dashboard provisioning, RBAC, container hardening, deterministic generation, and secret-shaped material.

## Immutable release candidate

A deployable candidate exists only when protected automation records all of:

```text
PROTECTED_SOURCE_SHA=<40-character SHA>
IMAGE=ghcr.io/appolon1908-hue/<approved-image>@sha256:<digest>
SOURCE_LABEL=<protected source SHA>
REVISION_LABEL=<protected source SHA>
CONFIGURATION_SHA256=<digest>
SBOM_SHA256=<digest>
PROVENANCE_SHA256=<digest>
SIGNATURE_VERIFICATION=PASS
```

A branch name, `latest`, `production`, `stable`, local image tag, pull-request merge ref, or unverified registry tag is not a production identity.

## Staging certification

Deploy the exact immutable candidate to isolated staging without rebuilding it. Required evidence:

- running digest equals the release candidate digest;
- `/api/health` is healthy and stable across repeated checks;
- expected Grafana version and commit labels are readable;
- OIDC discovery, login redirect, callback, logout, and role mapping pass;
- anonymous administrative access is disabled;
- Prometheus datasource health passes through the private service identity;
- provisioned folders and dashboards are present and read-only;
- datasource credentials do not appear in browser responses, dashboards, logs, or evidence;
- decoded dashboard content contains no retired PostgreSQL Exporter hostname;
- failure and degraded-state tests do not activate external effects;
- rollback to the previous immutable digest succeeds;
- the candidate can be reapplied after rollback without drift.

## Production cutover

Before mutation, record the current server, running image digest, configuration checksum, volume identity, database backup, secret mount names, edge route, health, and rollback digest. Do not record secret values.

Production deployment is allowed only after:

1. protected merge and exact merge-result checks pass;
2. the immutable candidate and attestations are verified;
3. staging certification and rollback rehearsal pass;
4. the active edge for `graf.codestra.media` is read back;
5. the `production` GitHub Environment or equivalent approved change authority authorizes the exact digest;
6. backup and restore ownership is documented;
7. automatic rollback triggers are defined.

Deploy by digest, start a canary or replacement without removing the working service, verify health and identity, then shift only the intended route. Do not restart Prometheus, PostgreSQL Exporter, Keycloak, or unrelated workloads.

## Required post-deployment evidence

```text
TARGET_SERVER=37.27.128.39
RUNNING_IMAGE_DIGEST=<immutable digest>
EXPECTED_IMAGE_DIGEST=<same immutable digest>
IMAGE_DIGEST_MATCH=PASS
CONFIGURATION_SHA256=<digest>
SOURCE_SHA=<protected merge SHA>
GRAFANA_HEALTH=PASS
OIDC=PASS
PROMETHEUS_DATASOURCE=PASS
ANONYMOUS_ADMIN=DISABLED
PUBLIC_POSTGRES_EXPORTER_ROUTE=ABSENT
ROLLBACK_DIGEST=<immutable digest>
ROLLBACK_AVAILABLE=PASS
WORKLOADS_RESTARTED=<Grafana only>
UNRELATED_WORKLOADS_RESTARTED=0
PRODUCTION_TRAFFIC_UNINTENTIONALLY_CHANGED=NO
```

Until that evidence exists, the correct result is `SOURCE_READY_RUNTIME_NOT_CERTIFIED`, not `PRODUCTION_LIVE`.
