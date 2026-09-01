#!/usr/bin/env python3
"""Validate protected-source and reviewed upstream-sync boundaries for Grafana."""

from __future__ import annotations

import json
import re
import shlex
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


def _shell_records(run: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return active shell lines with their enclosing executable context."""
    records: list[tuple[str, tuple[str, ...]]] = []
    frames: list[dict[str, str]] = []
    heredoc_end: str | None = None

    def context() -> tuple[str, ...]:
        rendered = []
        for frame in frames:
            if frame["kind"] == "if":
                rendered.append(
                    f"if:{frame['condition']}:{frame['branch']}"
                )
            else:
                rendered.append(f"{frame['kind']}:{frame['condition']}")
        return tuple(rendered)

    for raw_line in run.splitlines():
        line = raw_line.strip()
        if heredoc_end is not None:
            if line == heredoc_end:
                heredoc_end = None
            continue
        if not line or line.startswith("#"):
            continue
        if not frames and re.match(r"^(?:exit|return)(?:\s|$)", line):
            raise ValueError("top_level_shell_termination_forbidden")
        if re.match(
            r"^(?:function\s+)?[A-Za-z_][A-Za-z0-9_]*\s*\(\s*\)\s*(?:\{|$)",
            line,
        ) or re.match(r"^function\s+[A-Za-z_][A-Za-z0-9_]*(?:\s|$)", line):
            raise ValueError("shell_function_security_wrapper_forbidden")
        if re.match(r"^(?:for|while|until|select|case)\b", line):
            raise ValueError("unsupported_shell_control_flow")

        if line == "fi":
            if not frames or frames[-1]["kind"] != "if":
                raise ValueError("shell_control_flow_unbalanced")
            frames.pop()
            continue
        if line.startswith("elif ") and line.endswith("; then"):
            if not frames or frames[-1]["kind"] != "if":
                raise ValueError("shell_control_flow_unbalanced")
            condition = line[len("elif ") : -len("; then")].strip()
            frames[-1]["branch"] = f"elif:{condition}"
            continue
        if line == "else":
            if not frames or frames[-1]["kind"] != "if":
                raise ValueError("shell_control_flow_unbalanced")
            frames[-1]["branch"] = "else"
            continue
        if line.startswith("if ") and line.endswith("; then"):
            records.append((line, context()))
            frames.append(
                {
                    "kind": "if",
                    "condition": line[len("if ") : -len("; then")].strip(),
                    "branch": "then",
                }
            )
            continue
        if line.startswith(("if ", "elif ")):
            raise ValueError("unsupported_shell_control_flow")
        if line == "}":
            if not frames or frames[-1]["kind"] != "group":
                raise ValueError("shell_control_flow_unbalanced")
            frames.pop()
            continue

        records.append((line, context()))
        if (
            (line == "{" or line.endswith("&& {") or line.endswith("|| {"))
            and not line.endswith("; }")
        ):
            frames.append({"kind": "group", "condition": line})

        heredoc = re.search(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", line)
        if heredoc:
            heredoc_end = heredoc.group(2)

    if heredoc_end is not None or frames:
        raise ValueError("shell_control_flow_unbalanced")
    return tuple(records)


def _require_shell_context(
    records: tuple[tuple[str, tuple[str, ...]], ...],
    line: str,
    expected_context: tuple[str, ...] = (),
) -> None:
    contexts = [context for candidate, context in records if candidate == line]
    if contexts != [expected_context]:
        raise ValueError(f"executable_security_control_context_invalid:{line}")


def _shell_words(line: str) -> list[str]:
    try:
        lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        lexer.commenters = "#"
        return list(lexer)
    except ValueError as error:
        raise ValueError("shell_tokenization_failed") from error


def _logical_shell_records(
    records: tuple[tuple[str, tuple[str, ...]], ...]
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Join shell line continuations before security-sensitive tokenization."""

    logical: list[tuple[str, tuple[str, ...]]] = []
    continuation = ""
    continuation_context: tuple[str, ...] | None = None
    for line, context in records:
        if continuation:
            if context != continuation_context:
                raise ValueError("shell_continuation_context_invalid")
            line = continuation + line
        trailing_backslashes = len(line) - len(line.rstrip("\\"))
        if trailing_backslashes % 2 == 1:
            continuation = line[:-1]
            continuation_context = context
            continue
        logical.append((line, context))
        continuation = ""
        continuation_context = None
    if continuation:
        raise ValueError("shell_continuation_unbalanced")
    return tuple(logical)


def _reject_forbidden_pushes(
    records: tuple[tuple[str, tuple[str, ...]], ...]
) -> None:
    protected = {"main", "staging", "production"}
    separators = {";", "&&", "||", "|", "&"}
    for line, _context in _logical_shell_records(records):
        words = _shell_words(line)
        for index, word in enumerate(words):
            if word != "git":
                continue
            command_index = index + 1
            while command_index < len(words):
                option = words[command_index]
                if option in separators:
                    break
                if option in {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path"}:
                    command_index += 2
                    continue
                if option.startswith(
                    (
                        "--config-env=",
                        "--git-dir=",
                        "--work-tree=",
                        "--namespace=",
                        "--exec-path=",
                    )
                ) or option in {
                    "--bare",
                    "--no-replace-objects",
                    "--literal-pathspecs",
                    "--glob-pathspecs",
                    "--noglob-pathspecs",
                    "--icase-pathspecs",
                    "--no-optional-locks",
                    "-p",
                    "--paginate",
                    "-P",
                    "--no-pager",
                }:
                    command_index += 1
                    continue
                break
            if command_index >= len(words) or words[command_index] != "push":
                continue
            command: list[str] = []
            for word in words[command_index + 1 :]:
                if word in separators:
                    break
                command.append(word)
            if any(
                word in {"--force", "--force-with-lease", "-f"}
                or word.startswith("--force=")
                or word.startswith("--force-with-lease=")
                for word in command
            ):
                raise ValueError("protected_branch_sync_forbidden")
            if any(word in {"--all", "--branches", "--mirror"} for word in command):
                raise ValueError("protected_branch_sync_forbidden")
            for word in command:
                refspec = word.lstrip("+")
                if any(marker in refspec for marker in ("*", "?", "[")):
                    raise ValueError("protected_branch_sync_forbidden")
                destination = refspec.rsplit(":", 1)[-1]
                if destination.removeprefix("refs/heads/") in protected:
                    raise ValueError("protected_branch_sync_forbidden")


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
    steps = sync_job.get("steps")
    if not isinstance(steps, list) or [step.get("name") for step in steps] != [
        "Checkout Codestra authority",
        "Import official upstream source snapshot",
    ]:
        raise ValueError("sync_privileged_step_set_drift")
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
    records = _shell_records(run)
    _reject_forbidden_pushes(records)
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
    for line in (
        '[[ "$TRUSTED_UPSTREAM_REF" == "refs/heads/main" ]] || exit 2',
        '[[ "$UPSTREAM_REF" =~ ^[0-9a-f]{40}$ ]] || exit 2',
        'GIT_LFS_SKIP_SMUDGE=1 git -C .codestra-upstream-src fetch --filter=blob:none --no-tags origin "${TRUSTED_UPSTREAM_REF}:refs/remotes/origin/codestra-trusted"',
        'git -C .codestra-upstream-src merge-base --is-ancestor "$UPSTREAM_REF" refs/remotes/origin/codestra-trusted',
        '[[ "$UPSTREAM_SHA" == "$UPSTREAM_REF" ]] || exit 2',
        'SYNC_BRANCH="sync/grafana-upstream-${UPSTREAM_SHA}"',
        'git fetch --depth 1 --no-tags "$UPSTREAM_URL" "$UPSTREAM_SHA"',
        "git rm -r --cached --quiet --ignore-unmatch upstream",
        'git read-tree --prefix=upstream/ "${UPSTREAM_SHA}^{tree}"',
        'export GIT_AUTHOR_DATE="$UPSTREAM_TIMESTAMP"',
        'export GIT_COMMITTER_DATE="$UPSTREAM_TIMESTAMP"',
    ):
        _require_shell_context(records, line)
    _require_shell_context(
        records,
        'REMOTE_SHA="$(git ls-remote --heads origin "refs/heads/${SYNC_BRANCH}" | awk \'{print $1}\')"',
    )
    _require_shell_context(
        records,
        '[[ "$REMOTE_SHA" == "$LOCAL_SHA" ]] || {',
        ('if:[[ -n "$REMOTE_SHA" ]]:then',),
    )
    _require_shell_context(
        records,
        'git push origin "HEAD:refs/heads/${SYNC_BRANCH}"',
        ('if:[[ -n "$REMOTE_SHA" ]]:else',),
    )
    _require_shell_context(records, "gh pr list --repo \"$GITHUB_REPOSITORY\" --state open \\")
    _require_shell_context(
        records,
        "gh pr create \\",
        (
            "if:(( ${#OPEN_PRS[@]} > 1 )):elif:(( ${#OPEN_PRS[@]} == 0 ))",
        ),
    )
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
    if "if" in job or job.get("continue-on-error") not in {None, False}:
        raise ValueError("security_validation_job_must_be_unconditional_and_fatal")
    checkout = _step(job, "Check out exact head")
    if checkout.get("uses") != "actions/checkout@11d5960a326750d5838078e36cf38b85af677262" or checkout.get(
        "with"
    ) != {"persist-credentials": False, "fetch-depth": 0}:
        raise ValueError("validation_checkout_boundary_drift")
    setup = _step(job, "Set up Python")
    if setup.get("uses") != "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065":
        raise ValueError("validation_python_action_not_exactly_pinned")
    compile_step = _step(job, "Compile deterministic generators and validators")
    bind_step = _step(job, "Bind vendored Git tree to the pinned upstream commit")
    reject_step = _step(job, "Reject secret material and whitespace errors")
    for security_step in (compile_step, bind_step, reject_step):
        if "if" in security_step or security_step.get("continue-on-error") not in {
            None,
            False,
        }:
            raise ValueError("security_validation_step_must_be_unconditional_and_fatal")
    compile_lines = _active_lines(compile_step.get("run", ""))
    _require_active_line(compile_lines, "python scripts/validate_repository_security.py")
    compile_run = compile_step.get("run", "")
    _require_shell_context(
        _shell_records(compile_run), "python scripts/validate_repository_security.py"
    )
    bind_run = bind_step.get("run", "")
    bind_lines = _active_lines(bind_run)
    bind_records = _shell_records(bind_run)
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
        _require_shell_context(bind_records, line)
    reject_lines = _active_lines(
        reject_step.get("run", "")
    )
    _require_active_line(
        reject_lines,
        'git diff --check "$base_sha" "$GITHUB_SHA" -- . \':(exclude)upstream\'',
    )
    _require_shell_context(
        _shell_records(
            reject_step.get("run", "")
        ),
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
