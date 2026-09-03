#!/usr/bin/env python3
"""Render or deploy only the exact merged staging Grafana authority."""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


REPO = Path(__file__).resolve().parents[1]
COMPOSE = REPO / "codestra" / "deploy" / "staging" / "compose.yaml"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
CANONICAL_ROOT_URL = "https://graf.codestra.media/"
CANONICAL_REPOSITORY = "https://github.com/appolon1908-hue/Codestra-Grafana-.git"
CANONICAL_MAIN_REF = "refs/remotes/codestra-canonical/main"
GIT = "/usr/bin/git"
COMPOSE_BIN = "/usr/libexec/docker/cli-plugins/docker-compose"
GIT_ENVIRONMENT = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "XDG_CONFIG_HOME": "/nonexistent",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "LC_ALL": "C",
}


class PreflightError(RuntimeError):
    pass


def validate_deployment_identity() -> None:
    """Require the host authority that can validate root-owned secret files."""

    if os.geteuid() != 0:
        raise PreflightError(
            "staging Grafana deployment must run as root so root-owned "
            "secret files can be validated without weakening their ownership"
        )


def validate_isolated_interpreter() -> None:
    """Require a startup mode that cannot import from the checkout."""

    if not sys.flags.isolated:
        raise PreflightError(
            "deployment must invoke /usr/bin/python3 with -I so imports cannot "
            "be resolved from the checkout before source protection is validated"
        )


def _validate_protected_path(path: Path, label: str, required_uid: int) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise PreflightError(f"{label} could not be inspected") from exc
    if stat.S_ISLNK(info.st_mode):
        raise PreflightError(f"{label} must not be a symbolic link")
    if info.st_uid != required_uid:
        raise PreflightError(f"{label} has the wrong owner")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise PreflightError(f"{label} must not be group- or other-writable")


def _validate_protected_tree(path: Path, label: str, required_uid: int) -> None:
    _validate_protected_path(path, label, required_uid)
    for directory, names, files in os.walk(path, followlinks=False):
        directory_path = Path(directory)
        _validate_protected_path(directory_path, label, required_uid)
        for name in (*names, *files):
            _validate_protected_path(directory_path / name, label, required_uid)


def validate_protected_checkout(
    repo: Path = REPO,
    *,
    required_uid: int = 0,
    ancestry_root: Path = Path("/"),
) -> None:
    """Reject deployment from source another host account can replace."""

    if not repo.is_absolute() or repo.is_symlink():
        raise PreflightError("deployment checkout must be an absolute non-symlink path")
    if not ancestry_root.is_absolute() or repo != ancestry_root:
        try:
            repo.relative_to(ancestry_root)
        except ValueError as exc:
            raise PreflightError("deployment checkout is outside protected ancestry") from exc
    current = repo
    while True:
        _validate_protected_path(
            current, "deployment checkout ancestry", required_uid
        )
        if current == ancestry_root:
            break
        if current == current.parent:
            raise PreflightError("protected ancestry root was not reached")
        current = current.parent

    git_directory = repo / ".git"
    if not git_directory.is_dir() or git_directory.is_symlink():
        raise PreflightError(
            "deployment checkout must be a standalone protected Git checkout"
        )
    _validate_protected_tree(
        git_directory, "deployment Git metadata", required_uid
    )
    _validate_protected_path(
        repo / "scripts",
        "deployment entrypoint parent",
        required_uid,
    )
    _validate_protected_path(
        repo / "scripts" / "deploy_staging_runtime.py",
        "deployment entrypoint",
        required_uid,
    )
    _validate_protected_tree(
        repo / "codestra" / "deploy" / "staging",
        "deployment runtime source",
        required_uid,
    )


def git_output(*args: str) -> str:
    result = subprocess.run(
        [GIT, *args],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
        env=GIT_ENVIRONMENT,
    )
    if result.returncode != 0:
        raise PreflightError("Git source identity could not be verified")
    return result.stdout.strip()


def validate_source(source_sha: str, *, require_merged: bool) -> None:
    if not SHA40.fullmatch(source_sha):
        raise PreflightError("source SHA must be exactly 40 lowercase hexadecimal characters")
    if git_output("rev-parse", "HEAD") != source_sha:
        raise PreflightError("source SHA does not match the checked-out exact head")
    if git_output("status", "--porcelain"):
        raise PreflightError("deployment checkout is not clean")
    if require_merged:
        refreshed = subprocess.run(
            [
                GIT,
                "fetch",
                "--quiet",
                "--no-tags",
                CANONICAL_REPOSITORY,
                f"+refs/heads/main:{CANONICAL_MAIN_REF}",
            ],
            cwd=REPO,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            env=GIT_ENVIRONMENT,
        )
        if refreshed.returncode != 0:
            raise PreflightError("canonical main branch could not be refreshed")
        merged = subprocess.run(
            [GIT, "merge-base", "--is-ancestor", source_sha, CANONICAL_MAIN_REF],
            cwd=REPO,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            env=GIT_ENVIRONMENT,
        )
        if merged.returncode != 0:
            raise PreflightError("source SHA is not merged into canonical main")


def validate_root_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        value != CANONICAL_ROOT_URL
        or parsed.scheme != "https"
        or parsed.hostname != "graf.codestra.media"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise PreflightError(
            f"Grafana root URL must be exactly {CANONICAL_ROOT_URL}"
        )
    return value


def validate_secret_ancestry(
    directory: Path,
    label: str,
    *,
    required_uid: int = 0,
    ancestry_root: Path = Path("/"),
) -> None:
    if not directory.is_absolute() or not ancestry_root.is_absolute():
        raise PreflightError(f"{label} ancestry must be absolute")
    try:
        directory.relative_to(ancestry_root)
    except ValueError as exc:
        raise PreflightError(f"{label} is outside protected ancestry") from exc
    current = directory
    while True:
        _validate_protected_path(current, f"{label} ancestry", required_uid)
        if not current.is_dir():
            raise PreflightError(f"{label} ancestry must contain only directories")
        if current == ancestry_root:
            break
        if current == current.parent:
            raise PreflightError(f"{label} protected ancestry root was not reached")
        current = current.parent


def validate_secret_file(
    path: Path,
    label: str,
    *,
    required_file_uid: int = 0,
    required_file_gid: int = 0,
    required_ancestry_uid: int = 0,
    ancestry_root: Path = Path("/"),
) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise PreflightError(f"{label} must be an absolute non-symlink file")
    absolute = Path(os.path.abspath(path))
    resolved = path.resolve(strict=True)
    if absolute != resolved:
        raise PreflightError(f"{label} ancestry must not contain symbolic links")
    validate_secret_ancestry(
        resolved.parent,
        label,
        required_uid=required_ancestry_uid,
        ancestry_root=ancestry_root,
    )
    info = resolved.stat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_size < 32
        or info.st_size > 4096
    ):
        raise PreflightError(f"{label} is missing or malformed")
    if (info.st_uid, info.st_gid) != (required_file_uid, required_file_gid):
        raise PreflightError(f"{label} has the wrong owner or group")
    if stat.S_IMODE(info.st_mode) != 0o440:
        raise PreflightError(f"{label} mode must be 0440")
    descriptor = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise PreflightError(f"{label} changed during validation")
        raw = stream.read(4097)
    validate_secret_content(raw, label)
    return resolved


def validate_secret_content(raw: bytes, label: str) -> None:
    # Grafana's container entrypoint loads __FILE values with shell command
    # substitution, which removes trailing LF bytes. Validate that exact value.
    effective = raw.rstrip(b"\n")
    if not 32 <= len(effective) <= 4096:
        raise PreflightError(f"{label} effective value is missing or malformed")
    if any(byte < 0x21 or byte > 0x7E for byte in effective):
        raise PreflightError(f"{label} effective value must be visible ASCII")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("render", "deploy"), required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--root-url", required=True)
    parser.add_argument("--admin-password-file", type=Path, required=True)
    parser.add_argument("--secret-key-file", type=Path, required=True)
    args = parser.parse_args()

    if args.mode == "deploy":
        validate_isolated_interpreter()
        validate_deployment_identity()
        validate_protected_checkout()
    validate_source(args.source_sha, require_merged=args.mode == "deploy")
    root_url = validate_root_url(args.root_url)
    admin_file = (
        validate_secret_file(args.admin_password_file, "Grafana admin password")
        if args.mode == "deploy"
        else args.admin_password_file
    )
    key_file = (
        validate_secret_file(args.secret_key_file, "Grafana state secret")
        if args.mode == "deploy"
        else args.secret_key_file
    )
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent",
        "DOCKER_CONFIG": "/nonexistent",
        "LC_ALL": "C",
        "GRAFANA_SOURCE_SHA": args.source_sha,
        "GRAFANA_ROOT_URL": root_url,
        "GRAFANA_ADMIN_PASSWORD_FILE": str(admin_file),
        "GRAFANA_SECRET_KEY_FILE": str(key_file),
    }
    command = [COMPOSE_BIN, "-f", str(COMPOSE)]
    if args.mode == "render":
        command.extend(("config", "--quiet"))
    else:
        command.extend(
            (
                "up",
                "-d",
                "--no-deps",
                "--force-recreate",
                "--wait",
                "--wait-timeout",
                "120",
                "grafana",
            )
        )
    result = subprocess.run(
        command,
        cwd=REPO,
        env=environment,
        check=False,
        timeout=180,
    )
    if result.returncode != 0:
        raise PreflightError(f"staging Grafana {args.mode} failed")
    print(f"GRAFANA_STAGING_{args.mode.upper()}=PASS")
    print(f"GRAFANA_SOURCE_SHA={args.source_sha}")
    print("SECCOMP_DISABLED=NO")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired, PreflightError) as exc:
        print(f"GRAFANA_STAGING_PREFLIGHT=FAIL: {exc}")
        raise SystemExit(1)
