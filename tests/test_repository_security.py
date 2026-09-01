#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_repository_security", ROOT / "scripts/validate_repository_security.py"
)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class RepositorySecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sync_source = (ROOT / ".github/workflows/upstream-source-sync.yml").read_text()
        self.sync_document = yaml.safe_load(self.sync_source)

    def test_current_repository_security_contract(self) -> None:
        VALIDATOR.validate_repository()

    def test_mutable_upstream_ref_is_rejected(self) -> None:
        source = json.loads((ROOT / "CODESTRA_UPSTREAM.json").read_text())
        lock = json.loads((ROOT / "CODESTRA_UPSTREAM_LOCK.json").read_text())
        source["upstream_ref"] = "main"
        with self.assertRaisesRegex(ValueError, "upstream_ref_must_be_exact_commit"):
            VALIDATOR.validate_upstream(source, lock)

    def test_upstream_sync_uses_reviewed_pr_not_protected_branch_push(self) -> None:
        VALIDATOR.validate_sync(self.sync_source, self.sync_document)
        unsafe = self.sync_source.replace(
            'git push origin "HEAD:refs/heads/${SYNC_BRANCH}"',
            "git push origin HEAD:main",
        )
        with self.assertRaisesRegex(ValueError, "protected_branch_sync_forbidden"):
            VALIDATOR.validate_sync(unsafe, self.sync_document)

    def test_sync_rejects_full_protected_ref_and_noop_controls(self) -> None:
        full_ref = self.sync_source.replace(
            'git push origin "HEAD:refs/heads/${SYNC_BRANCH}"',
            "git push origin HEAD:refs/heads/main",
        )
        with self.assertRaisesRegex(ValueError, "protected_branch_sync_forbidden"):
            VALIDATOR.validate_sync(full_ref, yaml.safe_load(full_ref))
        for quoted_ref in (
            'git push origin "HEAD:refs/heads/main"',
            "git push origin 'HEAD:refs/heads/main'",
            'git push origin "+HEAD:refs/heads/main"',
        ):
            with self.subTest(quoted_ref=quoted_ref):
                unsafe = self.sync_source.replace(
                    'git push origin "HEAD:refs/heads/${SYNC_BRANCH}"', quoted_ref
                )
                with self.assertRaisesRegex(
                    ValueError, "protected_branch_sync_forbidden"
                ):
                    VALIDATOR.validate_sync(unsafe, yaml.safe_load(unsafe))
        for replacement in (
            '# git push origin "HEAD:refs/heads/${SYNC_BRANCH}"',
            'echo \'git push origin "HEAD:refs/heads/${SYNC_BRANCH}"\'',
        ):
            with self.subTest(replacement=replacement):
                no_op = self.sync_source.replace(
                    'git push origin "HEAD:refs/heads/${SYNC_BRANCH}"', replacement
                )
                with self.assertRaisesRegex(ValueError, "executable_security_control_missing"):
                    VALIDATOR.validate_sync(no_op, yaml.safe_load(no_op))

    def test_sync_rejects_protected_push_after_git_global_options(self) -> None:
        safe_push = 'git push origin "HEAD:refs/heads/${SYNC_BRANCH}"'
        for unsafe_push in (
            "git -c color.ui=false push origin HEAD:refs/heads/main",
            "git -C . push origin HEAD:refs/heads/staging",
            "git --git-dir=.git push origin +HEAD:refs/heads/production",
        ):
            with self.subTest(unsafe_push=unsafe_push):
                unsafe = self.sync_source.replace(safe_push, unsafe_push)
                with self.assertRaisesRegex(
                    ValueError, "protected_branch_sync_forbidden"
                ):
                    VALIDATOR.validate_sync(unsafe, yaml.safe_load(unsafe))

    def test_required_controls_must_be_in_reachable_shell_context(self) -> None:
        merge_base = (
            'git -C .codestra-upstream-src merge-base --is-ancestor '
            '"$UPSTREAM_REF" refs/remotes/origin/codestra-trusted'
        )
        unreachable = self.sync_source.replace(
            merge_base,
            "if false; then\n          " + merge_base + "\n          fi",
        )
        with self.assertRaisesRegex(
            ValueError, "executable_security_control_context_invalid"
        ):
            VALIDATOR.validate_sync(unreachable, yaml.safe_load(unreachable))

        safe_push = 'git push origin "HEAD:refs/heads/${SYNC_BRANCH}"'
        wrapped_push = self.sync_source.replace(
            safe_push,
            "if false; then\n            " + safe_push + "\n            fi",
        )
        with self.assertRaisesRegex(
            ValueError, "executable_security_control_context_invalid"
        ):
            VALIDATOR.validate_sync(wrapped_push, yaml.safe_load(wrapped_push))

        function_wrapped = self.sync_source.replace(
            merge_base,
            "dead_lineage_check() {\n          " + merge_base + "\n          }",
        )
        with self.assertRaisesRegex(
            ValueError, "shell_function_security_wrapper_forbidden"
        ):
            VALIDATOR.validate_sync(function_wrapped, yaml.safe_load(function_wrapped))

        validation = (
            ROOT / ".github/workflows/validate-codestra-observability.yml"
        ).read_text()
        validation_merge_base = (
            'git -C "$staging/source" merge-base --is-ancestor '
            '"$upstream_ref" refs/remotes/origin/codestra-trusted'
        )
        dead_validation = validation.replace(
            validation_merge_base,
            "if false; then\n          " + validation_merge_base + "\n          fi",
        )
        with self.assertRaisesRegex(
            ValueError, "executable_security_control_context_invalid"
        ):
            VALIDATOR.validate_workflow(dead_validation)

        terminated = self.sync_source.replace(
            "set -Eeuo pipefail", "set -Eeuo pipefail\n          exit 0", 1
        )
        with self.assertRaisesRegex(
            ValueError, "top_level_shell_termination_forbidden"
        ):
            VALIDATOR.validate_sync(terminated, yaml.safe_load(terminated))

    def test_validation_is_unconditional_and_actions_are_pinned(self) -> None:
        source = (ROOT / ".github/workflows/validate-codestra-observability.yml").read_text()
        VALIDATOR.validate_workflow(source)
        with self.assertRaisesRegex(ValueError, "pull_request_validation_must_be_unconditional"):
            VALIDATOR.validate_workflow(source.replace("pull_request:\n", "pull_request:\n    paths:\n      - codestra/**\n"))
        commented = source.replace(
            "python scripts/validate_repository_security.py",
            "# python scripts/validate_repository_security.py",
        )
        with self.assertRaisesRegex(ValueError, "executable_security_control_missing"):
            VALIDATOR.validate_workflow(commented)
        step_name = "      - name: Bind vendored Git tree to the pinned upstream commit\n"
        for property_line in (
            "        continue-on-error: true\n",
            "        if: false\n",
        ):
            with self.subTest(property_line=property_line):
                weakened = source.replace(step_name, step_name + property_line)
                with self.assertRaisesRegex(
                    ValueError,
                    "security_validation_step_must_be_unconditional_and_fatal",
                ):
                    VALIDATOR.validate_workflow(weakened)

    def test_pinned_commit_must_descend_from_trusted_upstream_ref(self) -> None:
        source = json.loads((ROOT / "CODESTRA_UPSTREAM.json").read_text())
        lock = json.loads((ROOT / "CODESTRA_UPSTREAM_LOCK.json").read_text())
        source["trusted_upstream_ref"] = "refs/pull/1/head"
        with self.assertRaisesRegex(ValueError, "grafana_upstream_drift:trusted_upstream_ref"):
            VALIDATOR.validate_upstream(source, lock)

    def test_generated_sync_pr_is_dispatched_for_exact_branch_validation(self) -> None:
        self.assertEqual(
            self.sync_document["permissions"],
            {"actions": "write", "contents": "write", "pull-requests": "write"},
        )
        self.assertIn("gh workflow run validate-codestra-observability.yml", self.sync_source)
        self.assertIn('--ref "$SYNC_BRANCH"', self.sync_source)
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/validate-codestra-observability.yml").read_text()
        )
        triggers = workflow.get("on") or workflow.get(True) or {}
        self.assertIn("workflow_dispatch", triggers)

    def test_vendored_tree_is_compared_to_fresh_exact_upstream_commit(self) -> None:
        source = (ROOT / ".github/workflows/validate-codestra-observability.yml").read_text()
        self.assertIn('fetch --filter=blob:none --no-tags origin "${trusted_upstream_ref}:refs/remotes/origin/codestra-trusted"', source)
        self.assertIn('merge-base --is-ancestor "$upstream_ref" refs/remotes/origin/codestra-trusted', source)
        self.assertIn('rev-parse HEAD)" == "$upstream_ref"', source)
        self.assertIn("rev-parse 'HEAD^{tree}'", source)
        self.assertIn('git rev-parse "HEAD:${import_path}"', source)
        self.assertIn('[[ "$vendored_tree" == "$official_tree" ]]', source)
        self.assertIn('git fetch --depth 1 --no-tags "$UPSTREAM_URL" "$UPSTREAM_SHA"', self.sync_source)
        self.assertIn('git read-tree --prefix=upstream/ "${UPSTREAM_SHA}^{tree}"', self.sync_source)

    def test_interrupted_sync_retry_reuses_only_identical_branch_and_pr(self) -> None:
        required = (
            'UPSTREAM_TIMESTAMP="$(git -C .codestra-upstream-src show -s --format=%cI "$UPSTREAM_SHA")"',
            'export GIT_AUTHOR_DATE="$UPSTREAM_TIMESTAMP"',
            'export GIT_COMMITTER_DATE="$UPSTREAM_TIMESTAMP"',
            '[[ "$REMOTE_SHA" == "$LOCAL_SHA" ]]',
            'gh pr list --repo "$GITHUB_REPOSITORY" --state open',
            "if (( ${#OPEN_PRS[@]} > 1 )); then",
        )
        for token in required:
            self.assertIn(token, self.sync_source)

    def test_whitespace_gate_checks_the_committed_base_to_head_range(self) -> None:
        source = (ROOT / ".github/workflows/validate-codestra-observability.yml").read_text()
        self.assertIn("fetch-depth: 0", source)
        self.assertIn('base_sha="${{ github.event.pull_request.base.sha }}"', source)
        self.assertIn(
            'git diff --check "$base_sha" "$GITHUB_SHA" -- . \':(exclude)upstream\'',
            source,
        )

if __name__ == "__main__":
    unittest.main(verbosity=2)
