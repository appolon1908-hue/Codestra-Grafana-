#!/usr/bin/env python3
"""Validate protected-source and reviewed upstream-sync boundaries for Grafana."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_PATH = ROOT / "CODESTRA_UPSTREAM.json"
LOCK_PATH = ROOT / "CODESTRA_UPSTREAM_LOCK.json"
SYNC_PATH = ROOT / ".github/workflows/upstream-source-sync.yml"
VALIDATE_PATH = ROOT / ".github/workflows/validate-codestra-observability.yml"


def _job(document: dict, name: str) -> dict:
    job = (document.get("jobs") or {}).get(name)
    if not isinstance(job, dict):
        raise ValueError(f"workflow_job_missing:{name}")
    return job


def _step(job: dict, name: str) -> dict:
    matches = [step for step in job.get("steps") or [] if step.get("name") == name]
    if len(matches) != 1:
        raise ValueError(f"workflow_step_identity_invalid:{name}")
    return matches[0]


def _active_lines(run: str) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in run.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _require_active_line(lines: tuple[str, ...], line: str) -> None:
    if line not in lines:
        raise ValueError(f"executable_security_control_missing:{line}")


def validate_upstream(source: dict, lock: dict) -> None:
    expected = {
        "upstream_clone_url": "https://github.com/grafana/grafana.git",
        "trusted_upstream_ref": "refs/heads/main",
        "import_path": "upstream",
        "deployment_enabled": False,
    }
    for key, value in expected.items():
        if source.get(key) != value or lock.get(key) != value:
            raise ValueError(f"grafana_upstream_drift:{key}")
    upstream_ref = source.get("upstream_ref")
    if not isinstance(upstream_ref, str) or re.fullmatch(r"[0-9a-f]{40}", upstream_ref) is None:
        raise ValueError("upstream_ref_must_be_exact_commit")
    if lock.get("upstream_ref") != upstream_ref or lock.get("upstream_commit") != upstream_ref:
        raise ValueError("upstream_lock_not_bound_to_exact_ref")


def validate_sync(source: str, document: dict) -> None:
    parsed = yaml.safe_load(source)
    if not isinstance(parsed, dict):
        raise ValueError("sync_workflow_document_invalid")
    document = parsed
    permissions = document.get("permissions") or {}
    if permissions != {
        "actions": "write",
        "contents": "write",
        "pull-requests": "write",
    }:
        raise ValueError("sync_permissions_drift")
    sync_job = _job(document, "sync")
    checkout = _step(sync_job, "Checkout Codestra authority")
    if checkout.get("uses") != "actions/checkout@11d5960a326750d5838078e36cf38b85af677262":
        raise ValueError("sync_checkout_action_not_exactly_pinned")
    import_step = _step(sync_job, "Import official upstream source snapshot")
    if import_step.get("shell") != "bash" or (import_step.get("env") or {}).get(
        "GH_TOKEN"
    ) != "${{ github.token }}":
        raise ValueError("sync_execution_boundary_drift")
    run = import_step.get("run")
    if not isinstance(run, str):
        raise ValueError("sync_run_script_missing")
    lines = _active_lines(run)
    active_source = "\n".join(lines)
    command_boundary = r"(?:^|(?:;|&&|\|\|)\s*)"
    protected_ref = r"(?:HEAD:)?(?:refs/heads/)?(?:main|staging|production)"
    if re.search(
        command_boundary + r"git\s+push\s+origin\s+" + protected_ref + r"(?:\s|$)",
        active_source,
        re.MULTILINE,
    ) or re.search(
        command_boundary + r"git\s+push\b[^\n]*(?:--force(?:-with-lease)?|-f)(?:\s|$)",
        active_source,
        re.MULTILINE,
    ):
        raise ValueError("protected_branch_sync_forbidden")
    required_lines = (
        '[[ "$TRUSTED_UPSTREAM_REF" == "refs/heads/main" ]] || exit 2',
        '[[ "$UPSTREAM_REF" =~ ^[0-9a-f]{40}$ ]] || exit 2',
        '[[ "$UPSTREAM_SHA" == "$UPSTREAM_REF" ]] || exit 2',
        'GIT_LFS_SKIP_SMUDGE=1 git -C .codestra-upstream-src fetch --filter=blob:none --no-tags origin "${TRUSTED_UPSTREAM_REF}:refs/remotes/origin/codestra-trusted"',
        'git -C .codestra-upstream-src merge-base --is-ancestor "$UPSTREAM_REF" refs/remotes/origin/codestra-trusted',
        'SYNC_BRANCH="sync/grafana-upstream-${UPSTREAM_SHA}"',
        'git push origin "HEAD:refs/heads/${SYNC_BRANCH}"',
        'git fetch --depth 1 --no-tags "$UPSTREAM_URL" "$UPSTREAM_SHA"',
        "git rm -r --cached --quiet --ignore-unmatch upstream",
        'git read-tree --prefix=upstream/ "${UPSTREAM_SHA}^{tree}"',
        'export GIT_AUTHOR_DATE="$UPSTREAM_TIMESTAMP"',
        'export GIT_COMMITTER_DATE="$UPSTREAM_TIMESTAMP"',
        "gh pr create \\",
        "--base main \\",
        "gh workflow run validate-codestra-observability.yml \\",
        '--repo "$GITHUB_REPOSITORY" --ref "$SYNC_BRANCH"',
        "'synchronized_at': os.environ['UPSTREAM_TIMESTAMP'],",
        'echo "Multiple open synchronization pull requests found." >&2',
    )
    for line in required_lines:
        _require_active_line(lines, line)
    for token in (
        "git ls-remote --heads origin",
        '[[ "$REMOTE_SHA" == "$LOCAL_SHA" ]]',
        "gh pr list",
        "if (( ${#OPEN_PRS[@]} > 1 )); then",
    ):
        if not any(token in line and not line.startswith(("echo ", "printf ")) for line in lines):
            raise ValueError(f"reviewed_sync_boundary_missing:{token}")


def validate_workflow(source: str) -> None:
    document = yaml.safe_load(source)
    triggers = document.get("on") or document.get(True) or {}
    if "pull_request" not in triggers or "workflow_dispatch" not in triggers:
        raise ValueError("validation_trigger_drift")
    if (triggers.get("push") or {}).get("branches") != ["main"]:
        raise ValueError("validation_push_branch_drift")
    if (document.get("permissions") or {}) != {"contents": "read"}:
        raise ValueError("validation_permissions_drift")
    job = _job(document, "validate-source")
    if job.get("name") != "validate-source":
        raise ValueError("validation_job_name_drift")
    checkout = _step(job, "Check out exact head")
    if checkout.get("uses") != "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" or checkout.get(
        "with"
    ) != {"persist-credentials": False, "fetch-depth": 0}:
        raise ValueError("validation_checkout_boundary_drift")
    setup = _step(job, "Set up Python")
    if setup.get("uses") != "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065":
        raise ValueError("validation_python_action_not_exactly_pinned")
    compile_lines = _active_lines(
        _step(job, "Compile deterministic generators and validators").get("run", "")
    )
    _require_active_line(compile_lines, "python scripts/validate_repository_security.py")
    bind_lines = _active_lines(
        _step(job, "Bind vendored Git tree to the pinned upstream commit").get("run", "")
    )
    for line in (
        "set -Eeuo pipefail",
        "[[ \"$trusted_upstream_ref\" == 'refs/heads/main' ]]",
        'GIT_LFS_SKIP_SMUDGE=1 git -C "$staging/source" fetch --filter=blob:none --no-tags origin "${trusted_upstream_ref}:refs/remotes/origin/codestra-trusted"',
        'git -C "$staging/source" merge-base --is-ancestor "$upstream_ref" refs/remotes/origin/codestra-trusted',
        '[[ "$(git -C "$staging/source" rev-parse HEAD)" == "$upstream_ref" ]]',
        'official_tree="$(git -C "$staging/source" rev-parse \'HEAD^{tree}\')"',
        'vendored_tree="$(git rev-parse "HEAD:${import_path}")"',
        '[[ "$vendored_tree" == "$official_tree" ]] || {',
    ):
        _require_active_line(bind_lines, line)
    reject_lines = _active_lines(
        _step(job, "Reject secret material and whitespace errors").get("run", "")
    )
    _require_active_line(
        reject_lines,
        'git diff --check "$base_sha" "$GITHUB_SHA" -- . \':(exclude)upstream\'',
    )
    uses = [step.get("uses") for step in job.get("steps") or [] if "uses" in step]
    if any(re.fullmatch(r"actions/(?:checkout|setup-python)@v\d+", item or "") for item in uses):
        raise ValueError("mutable_action_reference")
    if isinstance(triggers.get("pull_request"), dict) and "paths" in triggers["pull_request"]:
        raise ValueError("pull_request_validation_must_be_unconditional")
def validate_repository() -> None:
    for path in (UPSTREAM_PATH, LOCK_PATH, SYNC_PATH, VALIDATE_PATH):
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"required_regular_file_missing:{path.relative_to(ROOT)}")
    upstream = json.loads(UPSTREAM_PATH.read_text(encoding="utf-8"))
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    sync_source = SYNC_PATH.read_text(encoding="utf-8")
    sync_document = yaml.safe_load(sync_source)
    validate_source = VALIDATE_PATH.read_text(encoding="utf-8")
    validate_upstream(upstream, lock)
    validate_sync(sync_source, sync_document)
    validate_workflow(validate_source)
    if (ROOT / "upstream/.git").exists():
        raise ValueError("nested_upstream_git_metadata_forbidden")


if __name__ == "__main__":
    try:
        validate_repository()
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise SystemExit(f"GRAFANA_SOURCE_SECURITY=FAIL ERROR={error}") from error
    print("GRAFANA_SOURCE_SECURITY=PASS")
    print("UPSTREAM_COMMIT_PINNED=YES")
    print("SYNC_THROUGH_REVIEWED_PR=YES")
    print("VALIDATION_PATH_FILTER=NONE")
