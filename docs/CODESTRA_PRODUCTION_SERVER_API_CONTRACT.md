# Codestra Grafana Production Server and Native API Contract

## Authority

- Repository: `appolon1908-hue/Codestra-Grafana-`
- Role: read-only operational presentation and metrics/logs/traces correlation authority
- Canonical hostname: `graf.codestra.media`
- Central production host: `37.27.128.39`
- Status: `SOURCE_CONTRACT_PREPARED_NOT_DEPLOYED`

Grafana is the corporate operational interface. It does not own metrics retention, log or trace storage, alert delivery, business analytics, secret issuance, or application mutation.

## Native API surface

| Method | Path | Purpose | Boundary |
|---|---|---|---|
| `GET` | `/api/health` | health and database readiness | authenticated edge/read-only |
| `GET` | `/api/search` | dashboard/folder discovery | authenticated and role-scoped |
| `GET` | `/api/datasources` | datasource inventory metadata | authenticated users with `datasources:read`; in the shipped OSS model this includes Viewer |
| managed methods | dashboard APIs | source-managed dashboard provisioning | service identity only |
| managed methods | folder APIs | source-managed folder provisioning | service identity only |

Expected unauthenticated behavior may be an OIDC redirect, `401`, or `403`. Unexpected `404`, unhandled `5xx`, anonymous administration, or direct native-port access blocks production.

## Identity and isolation

- User login uses the approved Keycloak OIDC client and PKCE S256.
- Anonymous access and default credentials are disabled.
- Native Grafana publication remains loopback/private behind the approved edge.
- Datasources are fixed and provisioned from source; credentials come from OpenBao or approved secret files.
- The shipped Grafana OSS authorization model grants Viewer the fixed `datasources:read` permission when datasource-permission enforcement is unavailable. Production certification must not claim that `/api/datasources` is administrator-only.
- Datasource responses must not disclose decrypted passwords, tokens, private keys, cookies, authorization headers, or secure JSON values.
- A Loki datasource may link only to the matching business Tempo datasource.
- Folder permissions alone are not accepted as datasource isolation.
- Business user access remains disabled until organization-level isolation, datasource-level enforcement available in the deployed edition, or another reviewed equivalent boundary prevents cross-business datasource discovery and querying; negative cross-business tests must pass.
- Grafana is read-only with respect to business systems and cannot receive broker, exchange, custody, lender, payment, provider, or communications authority.

## Production gates

```text
PROTECTED_PRODUCTION_SHA=PASS
OIDC_CONFIGURATION=PASS
PKCE_S256=PASS
ROLE_MAPPING=PASS
ANONYMOUS_ACCESS=DISABLED
OSS_VIEWER_DATASOURCE_READ_MODEL=DOCUMENTED
DATASOURCE_PROVISIONING=PASS
DASHBOARD_PROVISIONING=PASS
ORGANIZATION_OR_DATASOURCE_ISOLATION=PASS
DATASOURCE_SECRET_FIELDS_EXPOSED=0
CROSS_BUSINESS_DENIAL=PASS
IMMUTABLE_IMAGE_DIGEST=PASS
IMAGE_SIGNATURE=PASS
SBOM=PASS
PROVENANCE=PASS
SECRET_SCAN=PASS
METADATA_BACKUP=PASS
METADATA_RESTORE=PASS
ROLLBACK_MANIFEST=PASS
```

## Runtime certification

```text
GET_/api/health=PASS
GET_/api/search_ROUTE_EXISTS=PASS
GET_/api/datasources_ROUTE_EXISTS=PASS
VIEWER_DATASOURCE_READ_BEHAVIOR=MATCHES_OSS_MODEL
DATASOURCE_SECRET_FIELDS_EXPOSED=0
OIDC_LOGIN=PASS
OIDC_LOGOUT=PASS
UNAUTHENTICATED_ADMIN_DENIED=PASS
ADMIN_MUTATION_FROM_VIEWER_DENIED=PASS
BUSINESS_USER_ACCESS_ENABLED=NO_UNTIL_ISOLATION_PROVEN
CROSS_ORGANIZATION_DATASOURCE_DISCOVERY_DENIED=PASS
WRONG_BUSINESS_QUERY_DENIED=PASS
PROMETHEUS_DATASOURCE=PASS
LOKI_DATASOURCE=PASS
TEMPO_DATASOURCE=PASS
LOG_TRACE_CORRELATION=PASS
UNEXPECTED_404=0
UNEXPECTED_5XX=0
SOURCE_RUNTIME_DRIFT=0
```

The datasource-read test must use the actual OSS permission model. It must not falsely interpret an expected authenticated Viewer response as an authorization bypass; the isolation test instead proves that no business user can discover or query another organization's datasource and that all secure fields remain redacted.

## Recovery and repository-first remediation

Back up and restore Grafana metadata and provisioning state before activation. Preserve the previous exact image digest and configuration. Any server defect must be fixed in this repository with tests, committed, pushed, reviewed, merged, rebuilt, signed, and added to the BOM before retrying.

## Safety

This source document does not deploy Grafana or enable user access. SSH changes, business writes, message delivery, provider effects, lending, payments, and trading remain disabled and outside scope.