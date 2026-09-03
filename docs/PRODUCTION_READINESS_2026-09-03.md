# Grafana production-readiness authority — 2026-09-03

## Candidate

```text
REPOSITORY=appolon1908-hue/Codestra-Grafana-
REPOSITORY_ID=1350767762
SOURCE_BASE=development@0d6e8259db6016294db910a3dbc38b4586c0927b
TARGET_BRANCH=main
TARGET_SERVER=37.27.128.39
PUBLIC_UI=graf.codestra.media
NATIVE_LISTENER=LOOPBACK_OR_PRIVATE_ONLY
SOURCE_STATE=CONFIG_PREPARED_NOT_DEPLOYED
PRODUCTION_ACTIVATION=DISABLED
```

This candidate consolidates the signed Grafana image-release work already accepted on `development` with the private PostgreSQL Exporter and stable repository-name controls. It does not import the older divergent `production` branch as runtime authority.

## Included production controls

- exact official Grafana 13.2.1 base image digest;
- repository-built, signed configuration image;
- exact-head and synthetic-merge validation;
- protected-commit validation;
- deterministic generation and image inclusion of the governed dashboard portfolio;
- source-provisioned, immutable Prometheus, Loki, Tempo, and Alertmanager datasources;
- Keycloak Authorization Code with PKCE, local-login denial, anonymous-access denial, and strict role mapping;
- external PostgreSQL with TLS verification and file-injected credentials;
- loopback-only host publication, private networks, read-only root filesystem, non-root runtime, dropped capabilities, no-new-privileges, health check, limits, and persistent metadata storage;
- redacted secret scanning, immutable source/image identity, backup/restore, upgrade, and rollback documentation;
- fail-closed private PostgreSQL Exporter policy and stable repository-ID aliases.

## Deliberately not activated

```text
GRAFANA_DEPLOYED=NO
KEYCLOAK_CLIENT_APPLIED=NO
DATASOURCES_CONNECTED=NO
BUSINESS_ACCESS_ENABLED=NO
DNS_CHANGED=NO
EDGE_RELOADED=NO
SECRETS_WRITTEN=NO
PRODUCTION_TRAFFIC_CHANGED=NO
```

## Remaining production cutover gates

1. Protected merge of the canonical candidate with qualifying independent approval.
2. Build and sign the exact accepted commit through `release-image.yml`.
3. Record the immutable Codestra Grafana image digest, SBOM, provenance, source revision, and vulnerability disposition.
4. Deploy that exact digest to isolated staging without rebuilding.
5. Prove `/api/health`, OIDC/PKCE, logout/session expiry, datasource health, dashboard provisioning, cross-business denial, CSP, backup/restore, and rollback.
6. Read back the active edge and authoritative runtime on `37.27.128.39`.
7. Preserve the current production digest and configuration as the rollback candidate.
8. Use a read-only production canary before any full promotion.

A repository merge is `SOURCE_READY`; it is not `PRODUCTION_LIVE` until the immutable artifact and runtime evidence are recorded.
