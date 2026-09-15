#!/usr/bin/env python3
"""Fail only on Clippy findings introduced on changed Rust lines."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def run_git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout


def normalize_path(value: str) -> str:
    path = value.replace("\\", "/")
    root = str(ROOT).replace("\\", "/")
    if path.startswith(root + "/"):
        return path[len(root) + 1 :]
    return path.removeprefix("b/")


def changed_ranges(base: str | None, worktree: bool = False) -> dict[str, list[range]]:
    args = ["diff", "--no-ext-diff", "--unified=0"]
    if base is not None:
        args.append(f"{base}...HEAD")
    elif worktree:
        args.append("HEAD")
    args.extend(["--", "*.rs", "build.rs"])
    diff = run_git(*args)
    ranges: dict[str, list[range]] = defaultdict(list)
    current_path: str | None = None

    for line in diff.splitlines():
        if line.startswith("+++ "):
            candidate = line[4:]
            current_path = None if candidate == "/dev/null" else normalize_path(candidate)
            continue
        if current_path is None:
            continue
        match = HUNK.match(line)
        if match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count:
            ranges[current_path].append(range(start, start + count))

    if worktree:
        untracked = run_git(
            "ls-files", "--others", "--exclude-standard", "-z", "--", "*.rs", "build.rs"
        )
        for path in filter(None, untracked.split("\0")):
            line_count = (ROOT / path).read_bytes().count(b"\n") + 1
            ranges[normalize_path(path)].append(range(1, line_count + 1))
    return ranges


def is_changed(ranges: dict[str, list[range]], path: str, line: int) -> bool:
    normalized = normalize_path(path)
    return any(line in changed for changed in ranges.get(normalized, []))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", help="Git ref used as the merge base")
    parser.add_argument(
        "--worktree",
        action="store_true",
        help="Check uncommitted changes instead of a committed range",
    )
    args = parser.parse_args()
    if args.base is not None and args.worktree:
        parser.error("--base and --worktree cannot be used together")

    ranges = changed_ranges(None if args.worktree else args.base, args.worktree)
    if not ranges:
        print("No changed Rust lines to check with Clippy.")
        return 0

    result = subprocess.run(
        [
            "cargo",
            "clippy",
            "--locked",
            "-p",
            "rustdesk",
            "--lib",
            "--no-deps",
            "--message-format=json",
            "--",
            "-W",
            "clippy::correctness",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    findings: list[tuple[str, int, str, str]] = []
    for line in result.stdout.splitlines():
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("reason") != "compiler-message":
            continue
        diagnostic = message["message"]
        code = diagnostic.get("code") or {}
        code_name = code.get("code", "")
        if not code_name.startswith("clippy::"):
            continue
        for span in diagnostic.get("spans", []):
            if span.get("is_primary") and is_changed(
                ranges, span["file_name"], span["line_start"]
            ):
                findings.append(
                    (
                        normalize_path(span["file_name"]),
                        span["line_start"],
                        code_name,
                        diagnostic["message"],
                    )
                )

    if result.returncode:
        sys.stderr.write(result.stderr)
        sys.stderr.write(result.stdout)
        return result.returncode

    if findings:
        print("Clippy findings on changed Rust lines:", file=sys.stderr)
        for path, line, code, message in findings:
            print(f"- {path}:{line}: {code}: {message}", file=sys.stderr)
        return 1

    print("No Clippy findings on changed Rust lines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
