# syntax=docker/dockerfile:1.7

ARG PYTHON_BUILDER_IMAGE
ARG GRAFANA_IMAGE

FROM ${PYTHON_BUILDER_IMAGE} AS dashboard-builder
WORKDIR /workspace
COPY codestra/business-registry.json codestra/business-registry.json
COPY codestra/provisioning/ codestra/provisioning/
COPY scripts/generate_codestra_dashboards.py scripts/generate_codestra_dashboards.py
COPY scripts/harden_codestra_dashboards.py scripts/harden_codestra_dashboards.py
RUN python3 -m py_compile \
      scripts/generate_codestra_dashboards.py \
      scripts/harden_codestra_dashboards.py \
    && python3 scripts/generate_codestra_dashboards.py \
    && python3 scripts/harden_codestra_dashboards.py \
    && test "$(find codestra/dashboards -type f -name '*.json' | wc -l)" -ge 40 \
    && test "$(find codestra/provisioning/intake-dashboards -type f -name '*.json' | wc -l)" -ge 1

FROM ${GRAFANA_IMAGE}
LABEL org.opencontainers.image.title="Codestra Corporate Grafana"
LABEL org.opencontainers.image.description="Source-controlled Codestra dashboards, datasources, SSO, and corporate operating boundaries"
LABEL org.opencontainers.image.vendor="Codestra"

COPY --chown=472:0 --chmod=0444 codestra/config/grafana.ini /etc/grafana/grafana.ini
COPY --from=dashboard-builder --chown=472:0 codestra/provisioning/ /etc/grafana/provisioning/
COPY --from=dashboard-builder --chown=472:0 codestra/dashboards/ /etc/grafana/codestra-dashboards/

USER 472:0
