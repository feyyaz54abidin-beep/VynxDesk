#!/usr/bin/env python3
"""Reject Android packages whose Flutter and VynxDesk native ABIs disagree."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def native_abis(entries: set[str], library: str) -> set[str]:
    suffix = f"/{library}"
    return {
        entry.split("/", 2)[1]
        for entry in entries
        if entry.startswith("lib/") and entry.endswith(suffix) and entry.count("/") == 2
    }


def validate_apk(path: Path) -> None:
    if not path.is_file():
        raise ValueError(f"APK does not exist: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = set(archive.namelist())
    except zipfile.BadZipFile as error:
        raise ValueError(f"Invalid APK archive: {path}") from error

    flutter_abis = native_abis(entries, "libflutter.so")
    rustdesk_abis = native_abis(entries, "librustdesk.so")
    cpp_abis = native_abis(entries, "libc++_shared.so")
    if not flutter_abis:
        raise ValueError(f"No Flutter runtime was packaged in {path}")

    problems: list[str] = []
    missing_core = sorted(flutter_abis - rustdesk_abis)
    if missing_core:
        problems.append("missing librustdesk.so for " + ", ".join(missing_core))
    orphaned_core = sorted(rustdesk_abis - flutter_abis)
    if orphaned_core:
        problems.append(
            "librustdesk.so has no matching Flutter ABI for " + ", ".join(orphaned_core)
        )
    missing_cpp = sorted(rustdesk_abis - cpp_abis)
    if missing_cpp:
        problems.append("missing libc++_shared.so for " + ", ".join(missing_cpp))
    if problems:
        raise ValueError(f"Native ABI validation failed for {path}: " + "; ".join(problems))

    print(
        f"Android APK native ABI validation passed: {path} "
        f"({', '.join(sorted(flutter_abis))})"
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"Usage: {Path(argv[0]).name} <apk> [<apk> ...]", file=sys.stderr)
        return 2
    try:
        for raw_path in argv[1:]:
            validate_apk(Path(raw_path).resolve())
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
