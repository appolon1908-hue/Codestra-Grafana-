# syntax=docker.io/docker/dockerfile@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG PYTHON_BUILDER_IMAGE
ARG GRAFANA_IMAGE

FROM ${PYTHON_BUILDER_IMAGE} AS dashboard-builder
WORKDIR /workspace
COPY codestra/business-registry.json codestra/business-registry.json
COPY scripts/generate_codestra_dashboards.py scripts/generate_codestra_dashboards.py
RUN python3 -m py_compile scripts/generate_codestra_dashboards.py \
    && python3 scripts/generate_codestra_dashboards.py \
    && test "$(find codestra/dashboards -type f -name '*.json' | wc -l)" -ge 40

FROM ${GRAFANA_IMAGE}
LABEL org.opencontainers.image.title="Codestra Corporate Grafana"
LABEL org.opencontainers.image.description="Source-controlled Codestra dashboards, datasources, SSO, and corporate operating boundaries"
LABEL org.opencontainers.image.vendor="Codestra"
LABEL codestra.artifact.model="repository-configured-signed-image"
LABEL codestra.upstream.executable-authority="grafana-v13.2.1-official-image"

COPY --chown=472:0 --chmod=0444 codestra/config/grafana.ini /etc/grafana/grafana.ini
COPY --chown=472:0 codestra/provisioning/ /etc/grafana/provisioning/
COPY --from=dashboard-builder --chown=472:0 /workspace/codestra/dashboards/ /etc/grafana/codestra-dashboards/
COPY --chown=472:0 --chmod=0444 codestra/release/image-build.v1.json /usr/share/codestra/image-build.v1.json
COPY --chown=472:0 --chmod=0444 codestra/release/runtime-base.lock.json /usr/share/codestra/runtime-base.lock.json
COPY --chown=472:0 --chmod=0444 codestra/runtime.v1.json /usr/share/codestra/runtime.v1.json

USER 472:0
