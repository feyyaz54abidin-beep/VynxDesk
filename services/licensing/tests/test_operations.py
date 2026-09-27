import importlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from cryptography.hazmat.primitives.asymmetric import ed25519

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service import LicenseStore


class OperatorAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = LicenseStore(Path(self.temp.name) / 'live.db', ed25519.Ed25519PrivateKey.generate())

    def tearDown(self):
        self.temp.cleanup()

    def journal(self, limit=100):
        self.assertTrue(hasattr(self.store, 'audit_events'), 'operator audit API is missing')
        return self.store.audit_events(limit=limit)

    def test_successful_mutations_are_audited_without_codes(self):
        license = self.store.issue(days=30, max_devices=2)
        self.store.extend(license['id'], days=5)
        new_code = self.store.rotate_code(license['id'])
        self.store.revoke(license['id'])
        events = self.journal()
        self.assertEqual([e['action'] for e in reversed(events)],
                         ['issue', 'extend', 'rotate-code', 'revoke'])
        self.assertEqual({e['license_id'] for e in events}, {license['id']})
        for e in events:
            self.assertIsInstance(e['occurred_at'], int)
            self.assertTrue(e['actor'])
        encoded = json.dumps(events)
        self.assertNotIn(license['code'], encoded)
        self.assertNotIn(new_code, encoded)
        self.assertNotIn('PRIVATE KEY', encoded)

    def test_failed_mutation_does_not_add_event(self):
        self.store.issue(days=1, max_devices=1)
        before = self.journal()
        with self.assertRaises(ValueError):
            self.store.extend('missing', days=3)
        self.assertEqual(self.journal(), before)

    def test_journal_failure_rolls_back_license_creation(self):
        self.journal()
        with self.store.connection() as db:
            db.execute("CREATE TRIGGER reject_audit BEFORE INSERT ON operator_events BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.Error):
            self.store.issue(days=1, max_devices=1)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM licenses').fetchone()[0], 0)

    def test_release_device_is_audited_and_limit_is_bounded(self):
        license = self.store.issue(days=1, max_devices=1)
        with self.store.connection() as db:
            db.execute('INSERT INTO devices VALUES(?,?,?,?,?,?)', ('device', license['id'], 'key', b'public', 1, 0))
        self.store.release_device(license['id'], 'device')
        self.assertEqual(self.journal(1)[0]['device_id'], 'device')
        self.assertEqual(self.journal(1)[0]['action'], 'release-device')
        for limit in [0, -1, 1001, True, '10']:
            with self.assertRaises(ValueError):
                self.store.audit_events(limit=limit)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'live.db'
        self.db = sqlite3.connect(self.source)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE samples(value TEXT)')
        self.db.execute("INSERT INTO samples VALUES('committed-in-wal')")
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def backup(self, output, source=None):
        self.assertTrue((Path(__file__).resolve().parents[1] / 'operations.py').exists(), 'online backup module is missing')
        return importlib.import_module('operations').backup_database(source or self.source, output)

    def test_committed_wal_rows_survive_backup(self):
        out = self.root / 'backup.db'
        result = self.backup(out)
        with sqlite3.connect(out) as db:
            self.assertEqual(db.execute('SELECT value FROM samples').fetchone()[0], 'committed-in-wal')
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(len(result['sha256']), 64)
        if os.name != 'nt':
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        self.assertFalse(Path(str(out) + '-wal').exists())

    def test_existing_destination_never_overwritten(self):
        out = self.root / 'existing.db'
        out.write_bytes(b'keep me')
        with self.assertRaises(FileExistsError): self.backup(out)
        self.assertEqual(out.read_bytes(), b'keep me')

    def test_missing_source_creates_nothing(self):
        missing = self.root / 'missing.db'
        out = self.root / 'backup.db'
        with self.assertRaises(FileNotFoundError): self.backup(out, missing)
        self.assertFalse(missing.exists())
        self.assertFalse(out.exists())

    def test_corrupt_source_leaves_no_backup(self):
        bad = self.root / 'bad.db'; bad.write_bytes(b'not SQLite')
        out = self.root / 'backup.db'
        with self.assertRaises(sqlite3.DatabaseError): self.backup(out, bad)
        self.assertFalse(out.exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX protected directory and symlink policy')
    def test_symlink_and_world_readable_directory_rejected(self):
        out = self.root / 'link.db'; out.symlink_to(self.source)
        with self.assertRaises(FileExistsError): self.backup(out)
        public = self.root / 'public'; public.mkdir(mode=0o755)
        with self.assertRaises(PermissionError): self.backup(public / 'backup.db')
        self.assertFalse((public / 'backup.db').exists())
