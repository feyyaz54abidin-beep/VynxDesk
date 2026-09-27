"""Offline operational utilities. Never expose these commands as public routes.
SPDX-License-Identifier: AGPL-3.0-or-later
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time


def backup_database(source: Path, destination: Path) -> dict:
    """Copy a live WAL database consistently; refuse overwrite and public folders."""
    source, destination = Path(source).absolute(), Path(destination).absolute()
    info = source.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('Source must be a regular database file')
    if source == destination:
        raise FileExistsError('Backup must not replace the live database')
    parent = destination.parent.stat()
    if os.name != 'nt' and parent.st_mode & 0o077:
        raise PermissionError('Backup directory must be accessible only to its owner')
    with source.open('rb') as src:
        if src.read(16) != b'SQLite format 3\x00':
            raise sqlite3.DatabaseError('Source is not a SQLite database')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    descriptor = os.open(destination, flags, 0o600)
    os.close(descriptor)
    deadline = time.monotonic() + 30

    def progress(status, remaining, total):
        if time.monotonic() >= deadline:
            raise TimeoutError('Database backup exceeded its deadline')

    src = dst = None
    try:
        src = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5)
        dst = sqlite3.connect(destination, timeout=5)
        src.backup(dst, pages=128, progress=progress, sleep=0.01)
        if dst.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise sqlite3.DatabaseError('Backup integrity check failed')
        dst.execute('PRAGMA journal_mode=DELETE')
        dst.close(); dst = None
        with destination.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            os.fsync(stream.fileno())
        return {'sha256': digest, 'bytes': destination.stat().st_size}
    except BaseException:
        if dst is not None:
            dst.close(); dst = None
        destination.unlink(missing_ok=True)
        for suffix in ('-wal', '-shm', '-journal'):
            Path(str(destination) + suffix).unlink(missing_ok=True)
        raise
    finally:
        if src is not None: src.close()
        if dst is not None: dst.close()


def main():
    parser = argparse.ArgumentParser(description='VYNX private database backup; not a source-export tool')
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        result = backup_database(Path(os.environ['VYNX_LICENSE_DB']), args.destination)
    except (OSError, ValueError, sqlite3.Error, KeyError):
        parser.exit(1, 'Backup failed; check source, private destination and free disk space.\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
