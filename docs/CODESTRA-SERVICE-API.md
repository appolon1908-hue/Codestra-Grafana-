# Codestra service API contract: Grafana

This repository owns the **read-only-operational-presentation-authority** for the Codestra observability, analytics, telemetry, and secrets suite.

## Communication rule

Grafana keeps its native API and protocol. The shared Codestra control plane in `appolon1908-hue/Codestra-Telemetry` performs only sanitized health, readiness, contract, topology, and immutable-release read-back. It never proxies native query bodies, ingestion, alert delivery, dashboard mutations, secret values, or credential issuance.

Canonical hostname: `graf.codestra.media`  
Native exposure: `loopback_edge_only`  
Deployment class: `central`  
Contract: `codestra/api/service-contract.v1.json`

## Native operations

| Method | Path | Category | Access | Control-plane rule |
|---|---|---|---|---|
| `GET` | `/api/health` | health | read_only | never proxied by the Codestra control API |
| `GET` | `/api/health` | readiness | read_only | never proxied by the Codestra control API |
| `GET` | `/api/search` | query | read_only | never proxied by the Codestra control API |
| `GET` | `/api/dashboards/uid/{uid}` | query | read_only | never proxied by the Codestra control API |
| `GET` | `/api/folders` | query | read_only | never proxied by the Codestra control API |
| `GET` | `/api/datasources` | query | read_only | never proxied by the Codestra control API |
| `GET` | `/api/datasources/uid/{uid}/health` | query | read_only | never proxied by the Codestra control API |
| `POST` | `/api/ds/query` | query | query | never proxied by the Codestra control API |

## Suite integrations

| Peer | Direction | Signal | Protocol | Purpose |
|---|---|---|---|---|
| `prometheus` | outbound | `metrics` | `prometheus-http-api` | query metrics and SLOs |
| `loki` | outbound | `logs` | `loki-http-api` | query business-isolated logs |
| `tempo` | outbound | `traces` | `tempo-http-api` | query traces and service graphs |
| `alertmanager` | outbound | `alerts` | `alertmanager-http-api` | read alert state |

## Identity and correlation

Every private request should propagate `X-Correlation-ID` and W3C `traceparent` when the native protocol supports them. `request_id`, `trace_id`, and `tenant_id` remain structured, protected, non-indexed fields. Metrics use only the bounded dimensions `codestra_business`, `application`, `service`, `environment`, `server`, `region`, and `deployment`.

Business identity is deployment-controlled. Caller-supplied business identity, cross-business defaults, anonymous management access, insecure TLS verification, and inline credentials are prohibited.

## Release and runtime boundary

The control plane reads source revision and image digest only from deployment environment variables. A valid release requires a 40-character Git SHA and `sha256:<64 lowercase hex>` image digest. This source change does not deploy the service, activate ingestion/scrapes/probes/alerts, issue credentials, or enable any business, communications, financial, or trading mutation.


## Contract authority handoff

- Canonical schema repository: `appolon1908-hue/Codestra-Telemetry`
- Canonical merged Telemetry SHA: `1ca489c9060d79f849eb7d656f9c85c4b4b56cac`
- Contract version: `1.0.0`
- Downstream exact head: this PR branch commit; the authoritative literal SHA is the GitHub PR `headRefOid` recorded after this handoff commit.
- Deployment authorization: unauthorized until staging certification and protected production promotion are complete.
