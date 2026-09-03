# Repository profile

- Authority: `appolon1908-hue/Codestra-Grafana-`
- Stable repository ID: `1350767762`
- Component: Grafana read-only corporate observability portal
- Production server authority: `37.27.128.39`
- Public UI contract: `https://graf.codestra.media` through the approved edge only
- Native Grafana listener: loopback/private only
- Artifact model: repository-built and signed Codestra configuration image
- Official runtime base: Grafana 13.2.1 at `sha256:f772d434e8fab0049deb2b1b30abd43342bcfca1537614aa8d36080232cf4283`
- Canonical deployment source: `codestra/deploy/compose.candidate.yaml`
- Canonical release workflow: `.github/workflows/release-image.yml`
- PostgreSQL Exporter: private-only dependency reached through Prometheus; never a Grafana browser datasource or public route
- Repository rename state: `PREPARED_NOT_RENAMED`
- Current source state: `CONFIG_PREPARED_NOT_DEPLOYED`
- Production activation: disabled pending protected promotion, signed artifact publication, staging certification, server readback, backup, and rollback evidence

The vendored unreleased upstream snapshot is retained only as reference and is not executable authority. A source merge or successful image build does not authorize DNS, Keycloak, datasource, database, server, or production-runtime mutation.
