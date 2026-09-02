#!/usr/bin/env bash
set -Eeuo pipefail

source_sha="${1:?exact source SHA is required}"
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]]
test "$(git rev-parse HEAD)" = "$source_sha"

builder="$(jq -r '.builderImage' codestra/release/runtime-base.lock.json)"
runtime="$(jq -r '.upstreamImage' codestra/release/runtime-base.lock.json)"
tag="local/codestra-grafana:${source_sha}"

docker build \
  --file codestra/deploy/Dockerfile \
  --build-arg "PYTHON_BUILDER_IMAGE=$builder" \
  --build-arg "GRAFANA_IMAGE=$runtime" \
  --tag "$tag" \
  .
docker run --rm --entrypoint /usr/share/grafana/bin/grafana "$tag" --version | grep -F 'grafana version 13.2.1'
test "$(docker image inspect "$tag" --format '{{.Config.User}}')" = '472:0'

container_id=""
cleanup() {
  if [[ -n "$container_id" ]]; then
    docker container rm "$container_id" >/dev/null
  fi
}
trap cleanup EXIT
container_id="$(docker create "$tag")"
evidence_dir="${RUNNER_TEMP:-/tmp}/grafana-image-${source_sha}"
mkdir -p "$evidence_dir"
docker cp "$container_id:/usr/share/codestra/image-build.v1.json" "$evidence_dir/image-build.v1.json"
docker cp "$container_id:/usr/share/codestra/runtime-base.lock.json" "$evidence_dir/runtime-base.lock.json"
docker cp "$container_id:/usr/share/codestra/runtime.v1.json" "$evidence_dir/runtime.v1.json"
cmp codestra/release/image-build.v1.json "$evidence_dir/image-build.v1.json"
cmp codestra/release/runtime-base.lock.json "$evidence_dir/runtime-base.lock.json"
cmp codestra/runtime.v1.json "$evidence_dir/runtime.v1.json"
echo "GRAFANA_LOCKED_IMAGE_INSPECTION=PASS"
