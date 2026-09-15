#!/usr/bin/env python3
"""Validate release-only inputs without printing protected configuration."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HBB_SUBMODULE = "libs/hbb_common"
RELEASE_ENV = (
    "VYNXDESK_RENDEZVOUS_SERVER",
    "VYNXDESK_RENDEZVOUS_PUB_KEY",
)


class ContractError(RuntimeError):
    pass


def run_git(*args: str, cwd: Path = ROOT) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ContractError(f"git command failed: {' '.join(args)}")
    return result.stdout.strip()


def read_gitlink() -> str:
    try:
        entry = run_git("ls-tree", "HEAD", "--", HBB_SUBMODULE)
    except ContractError as error:
        raise ContractError("libs/hbb_common is not present in the root tree") from error
    fields = entry.split(None, 3)
    if len(fields) != 4 or fields[0] != "160000" or fields[1] != "commit":
        raise ContractError("libs/hbb_common must be tracked as a commit submodule")
    return fields[2]


def read_submodule_url() -> str:
    try:
        url = run_git(
            "config",
            "-f",
            ".gitmodules",
            "--get",
            "submodule.libs/hbb_common.url",
        )
    except ContractError as error:
        raise ContractError("libs/hbb_common URL is missing from .gitmodules") from error
    if not url:
        raise ContractError("libs/hbb_common URL is empty")
    return url


def require_release_environment() -> None:
    missing = [name for name in RELEASE_ENV if not os.environ.get(name, "").strip()]
    if missing:
        raise ContractError(
            "missing required release environment: " + ", ".join(missing)
        )


def require_clean_root() -> None:
    if run_git("status", "--porcelain"):
        raise ContractError("the root worktree must be clean for a release build")


def verify_hbb_remote(url: str, commit: str) -> None:
    with tempfile.TemporaryDirectory(prefix="vynxdesk-hbb-contract-") as directory:
        probe = Path(directory)
        result = subprocess.run(
            [
                "git",
                "init",
                "--bare",
                "--quiet",
                str(probe),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise ContractError("could not initialize the submodule remote probe")
        result = subprocess.run(
            [
                "git",
                "-C",
                str(probe),
                "fetch",
                "--quiet",
                "--no-tags",
                url,
                f"{commit}:refs/heads/release-contract",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise ContractError(
                "the libs/hbb_common gitlink is not fetchable from its configured remote"
            )
        result = subprocess.run(
            ["git", "-C", str(probe), "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise ContractError("the fetched hbb_common gitlink is not a commit object")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-release-env",
        action="store_true",
        help="require the production rendezvous host and public key",
    )
    parser.add_argument(
        "--verify-hbb-remote",
        action="store_true",
        help="prove that the root hbb_common gitlink is fetchable remotely",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="allow a dirty root worktree (use only for diagnostics)",
    )
    args = parser.parse_args()

    commit = read_gitlink()
    url = read_submodule_url()
    if not args.allow_dirty:
        require_clean_root()
    if args.require_release_env:
        require_release_environment()
    if args.verify_hbb_remote:
        verify_hbb_remote(url, commit)

    print("Release contract validation passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"Release contract validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
