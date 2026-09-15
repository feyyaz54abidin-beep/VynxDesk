#!/usr/bin/env python3
"""Validate the version values shared by build, CI, and developer entry points."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def capture(pattern: str, content: str, label: str) -> str:
    match = re.search(pattern, content, re.MULTILINE)
    if match is None:
        raise ValueError(f"{label}: value was not found")
    return match.group(1)


def yaml_env_value(path: str, key: str) -> str:
    return capture(
        rf'^  {re.escape(key)}:\s*"([^"]+)"',
        read(path),
        f"{path}:{key}",
    )


def bridge_flutter_version(bridge: str, artifact_name: str) -> str:
    return capture(
        rf'flutter-version:\s*"([^\"]+)",\s*\n\s*artifact-name:\s*"{re.escape(artifact_name)}"',
        bridge,
        f".github/workflows/bridge.yml:{artifact_name}",
    )


def main() -> int:
    versions = tomllib.loads(read("toolchain-versions.toml"))["build"]
    cargo = read("Cargo.toml")
    bridge = read(".github/workflows/bridge.yml")
    flutter_build = read(".github/workflows/flutter-build.yml")
    release_preflight = read(".github/workflows/release-preflight.yml")
    vcpkg = json.loads(read("vcpkg.json"))

    checks = [
        (
            "Cargo rust-version",
            capture(r'^rust-version\s*=\s*"([^"]+)"', cargo, "Cargo.toml"),
            versions["application_rust"],
        ),
        (
            "Cargo flutter_rust_bridge",
            capture(
                r'^flutter_rust_bridge\s*=\s*\{\s*version\s*=\s*"([^"]+)"',
                cargo,
                "Cargo.toml:flutter_rust_bridge",
            ),
            versions["flutter_rust_bridge_rust"],
        ),
        (
            "native CI Rust",
            yaml_env_value(".github/workflows/ci.yml", "RUST_VERSION"),
            versions["application_rust"],
        ),
        (
            "bridge Rust",
            yaml_env_value(".github/workflows/bridge.yml", "RUST_VERSION"),
            versions["application_rust"],
        ),
        (
            "bridge codegen",
            yaml_env_value(".github/workflows/bridge.yml", "FLUTTER_RUST_BRIDGE_VERSION"),
            versions["flutter_rust_bridge_codegen"],
        ),
        (
            "bridge default Flutter",
            bridge_flutter_version(bridge, "bridge-artifact"),
            versions["bridge_default_flutter"],
        ),
        (
            "bridge Windows ARM Flutter",
            bridge_flutter_version(bridge, "bridge-artifact-flutter-3.44"),
            versions["bridge_windows_arm_flutter"],
        ),
        (
            "Flutter Rust",
            yaml_env_value(".github/workflows/flutter-build.yml", "RUST_VERSION"),
            versions["application_rust"],
        ),
        (
            "Flutter macOS Rust",
            yaml_env_value(".github/workflows/flutter-build.yml", "MAC_RUST_VERSION"),
            versions["application_rust"],
        ),
        (
            "legacy Sciter Rust",
            yaml_env_value(".github/workflows/flutter-build.yml", "SCITER_RUST_VERSION"),
            versions["legacy_sciter_rust"],
        ),
        (
            "Flutter default",
            yaml_env_value(".github/workflows/flutter-build.yml", "FLUTTER_VERSION"),
            versions["flutter"],
        ),
        (
            "Flutter Android",
            yaml_env_value(".github/workflows/flutter-build.yml", "ANDROID_FLUTTER_VERSION"),
            versions["android_flutter"],
        ),
        (
            "Flutter Windows ARM",
            yaml_env_value(".github/workflows/flutter-build.yml", "FLUTTER_WINDOWS_ARM_VERSION"),
            versions["windows_arm_flutter"],
        ),
        (
            "vcpkg baseline",
            vcpkg["vcpkg-configuration"]["default-registry"]["baseline"],
            versions["vcpkg_baseline"],
        ),
        (
            "native CI vcpkg baseline",
            yaml_env_value(".github/workflows/ci.yml", "VCPKG_COMMIT_ID"),
            versions["vcpkg_baseline"],
        ),
        (
            "Flutter CI vcpkg baseline",
            yaml_env_value(".github/workflows/flutter-build.yml", "VCPKG_COMMIT_ID"),
            versions["vcpkg_baseline"],
        ),
        (
            "release preflight Rust",
            yaml_env_value(".github/workflows/release-preflight.yml", "RUST_VERSION"),
            versions["application_rust"],
        ),
        (
            "release preflight vcpkg baseline",
            yaml_env_value(".github/workflows/release-preflight.yml", "VCPKG_COMMIT_ID"),
            versions["vcpkg_baseline"],
        ),
        (
            "Docker vcpkg baseline",
            capture(
                r'git (?:-C \S+ )?checkout ([0-9a-f]{40})',
                read("Dockerfile"),
                "Dockerfile",
            ),
            versions["vcpkg_baseline"],
        ),
        (
            "README vcpkg baseline",
            capture(r'git checkout ([0-9a-f]{40})', read("README.md"), "README.md"),
            versions["vcpkg_baseline"],
        ),
        (
            "CI cargo-audit",
            capture(
                r'cargo install cargo-audit --version ([0-9.]+) --locked',
                read(".github/workflows/ci.yml"),
                ".github/workflows/ci.yml:cargo-audit",
            ),
            versions["cargo_audit"],
        ),
        (
            "release preflight cargo-audit",
            capture(
                r'cargo install cargo-audit --version ([0-9.]+) --locked',
                release_preflight,
                ".github/workflows/release-preflight.yml:cargo-audit",
            ),
            versions["cargo_audit"],
        ),
    ]

    failures = [f"{label}: expected {expected}, found {actual}" for label, actual, expected in checks if actual != expected]
    if failures:
        print("Build contract validation failed:", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1

    print("Build contract validation passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"Build contract validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
