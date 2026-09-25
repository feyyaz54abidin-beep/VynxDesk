#!/usr/bin/env python3
"""Export exact, clean Git source and pinned submodules, never the working folder."""
from __future__ import annotations

import argparse
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile


class SourcePackageError(RuntimeError):
    pass


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    if result.returncode:
        # Git stderr can include authenticated remotes or other local configuration.
        raise SourcePackageError("Cannot read the exact Git source; check repository and submodule state")
    return result.stdout


def private_path(name: str) -> bool:
    path = PurePosixPath(name.lower())
    base = path.name
    return (
        base in {".env", "id_ed25519", "id_rsa", "id_ecdsa", "key.properties"}
        or (base.startswith(".env.") and base not in {".env.example", ".env.sample", ".env.template"})
        or path.suffix in {".pfx", ".p12", ".jks", ".keystore"}
    )


def collect_source(root: Path, prefix: str, expected: str | None,
                   files: dict[str, tuple[int, bytes]], submodules: dict[str, str]) -> str:
    if not root.is_dir():
        raise SourcePackageError("A required source submodule is not initialized")
    top = Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel").strip())).resolve()
    if top != root.resolve():
        raise SourcePackageError("A required source submodule is not initialized")
    commit = git(root, "rev-parse", "HEAD").decode("ascii").strip()
    if expected is not None and commit != expected:
        raise SourcePackageError("A submodule checkout does not match its pinned commit")
    dirty = git(root, "status", "--porcelain", "--untracked-files=no", "--ignore-submodules=untracked")
    if dirty:
        raise SourcePackageError("Tracked source has uncommitted changes; commit or discard them before packaging")
    entries = git(root, "ls-tree", "-r", "-z", commit).split(b"\0")
    blobs = []
    children = []
    for entry in entries:
        if not entry:
            continue
        header, raw_path = entry.split(b"\t", 1)
        mode, kind, object_id = header.decode("ascii").split()
        path = raw_path.decode("utf-8")
        name = prefix + path
        parts = PurePosixPath(name).parts
        if not parts or name.startswith("/") or any(part in {"..", ".git"} for part in parts) or "\\" in name:
            raise SourcePackageError("Source contains an unsupported archive path")
        if name == "VYNXDESK_SOURCE.json":
            raise SourcePackageError("Source collides with the reserved provenance filename")
        if private_path(name):
            raise SourcePackageError("Source contains a tracked credential or private-key filename; remove it before packaging")
        if kind == "commit":
            children.append((path, name, object_id))
        elif kind == "blob":
            blobs.append((name, int(mode, 8), object_id))
        else:
            raise SourcePackageError("Source contains an unsupported Git object type")
    if blobs:
        # One Git process per repository; use object IDs, not shell-interpolated paths.
        request = "".join(object_id + "\n" for _, _, object_id in blobs).encode("ascii")
        result = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"],
                                input=request, capture_output=True, check=False)
        if result.returncode:
            raise SourcePackageError("Cannot read source objects")
        stream = io.BytesIO(result.stdout)
        for name, mode, object_id in blobs:
            fields = stream.readline().split()
            if len(fields) != 3 or fields[0].decode("ascii") != object_id or fields[1] != b"blob":
                raise SourcePackageError("Invalid source object response")
            data = stream.read(int(fields[2]))
            if len(data) != int(fields[2]) or stream.read(1) != b"\n":
                raise SourcePackageError("Incomplete source object response")
            if b"-----BEGIN " in data and any(marker in data for marker in (
                b"PRIVATE KEY-----", b"PGP PRIVATE KEY BLOCK-----"
            )):
                # Detection patterns in source code are not PEM-encoded secrets.
                if any(line.startswith(b"-----BEGIN ") and b"PRIVATE KEY" in line for line in data.splitlines()):
                    raise SourcePackageError("Source contains a private-key block; remove it before packaging")
            if name in files:
                raise SourcePackageError("Source archive paths overlap")
            files[name] = (mode, data)
    for path, name, object_id in children:
        child = root / path
        if not child.resolve().is_relative_to(root.resolve()):
            raise SourcePackageError("Source submodule points outside its parent repository")
        collect_source(child, name + "/", object_id, files, submodules)
        submodules[name] = object_id
    return commit


def write_zip(path: Path, files: dict[str, tuple[int, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, (mode, data) in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = mode << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)


def write_tar_gz(path: Path, files: dict[str, tuple[int, bytes]]) -> None:
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for name, (mode, data) in sorted(files.items()):
                entry = tarfile.TarInfo(name)
                entry.mode = stat.S_IMODE(mode)
                if stat.S_ISLNK(mode):
                    entry.type = tarfile.SYMTYPE
                    entry.linkname = data.decode("utf-8")
                    archive.addfile(entry)
                else:
                    entry.size = len(data)
                    archive.addfile(entry, io.BytesIO(data))


def create_archive(root: Path, output: Path, force: bool = False) -> None:
    root = Path(root).resolve()
    output = Path(output).absolute()
    is_zip = output.name.lower().endswith(".zip")
    if not is_zip and not output.name.lower().endswith((".tar.gz", ".tgz")):
        raise SourcePackageError("Output must end with .zip, .tar.gz or .tgz")
    if output.is_symlink() or (output.exists() and not force):
        raise SourcePackageError("Output already exists or is a symlink")
    files: dict[str, tuple[int, bytes]] = {}
    submodules: dict[str, str] = {}
    commit = collect_source(root, "", None, files, submodules)
    # Recheck after reading to detect concurrent edits/checkouts before publication.
    if git(root, "rev-parse", "HEAD").decode("ascii").strip() != commit:
        raise SourcePackageError("Source revision changed while packaging")
    metadata = {"product": "VynxDesk", "commit": commit, "submodules": submodules,
                "format_version": 1, "source": "tracked Git objects at the specified commits"}
    files["VYNXDESK_SOURCE.json"] = (0o100644, (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".vynxdesk-source-", dir=output.parent)
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        (write_zip if is_zip else write_tar_gz)(temporary_path, files)
        if force:
            os.replace(temporary_path, output)
        else:
            # Atomic creation without clobbering a file created by a concurrent run.
            os.link(temporary_path, output)
    except FileExistsError as error:
        raise SourcePackageError("Output already exists") from error
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        create_archive(Path(__file__).resolve().parents[1], args.output, args.force)
    except (SourcePackageError, OSError, UnicodeError) as error:
        print(f"Source packaging failed: {error}", file=sys.stderr)
        return 1
    print(f"Exact source archive created: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
