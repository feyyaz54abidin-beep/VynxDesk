"""Regressions for externally supplied input and live database failures."""
import base64
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from service import LicenseStore, create_app


class RuntimeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'licenses.db'
        self.key = ed25519.Ed25519PrivateKey.generate()
        self.store = LicenseStore(self.path, self.key)
        self.client = TestClient(create_app(self.store), base_url='https://service.test',
                                 raise_server_exceptions=False)
        key = ec.generate_private_key(ec.SECP256R1())
        public = key.public_key().public_bytes(serialization.Encoding.DER,
                                              serialization.PublicFormat.SubjectPublicKeyInfo)
        self.body = json.dumps({'public_key': base64.b64encode(public).decode(),
                               'operation': 'activate', 'binding': 'a' * 64})

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def post(self, *, headers=None, body=None):
        return self.client.post('/v1/challenges', content=self.body if body is None else body,
                                headers=headers or {'Content-Type': 'application/json'})

    def test_huge_content_length_is_rejected_without_500(self):
        r = self.post(headers={'Content-Type': 'application/json', 'Content-Length': '9' * 5000})
        self.assertEqual(r.status_code, 413, r.text)
        self.assertEqual(r.json(), {'error': 'request_too_large'})

    def test_duplicate_length_headers_are_rejected(self):
        r = self.post(headers=[('content-type', 'application/json'),
                               ('content-length', str(len(self.body))), ('content-length', '1')])
        self.assertEqual(r.status_code, 400, r.text)

    def test_transfer_encoding_and_length_are_not_accepted_together(self):
        r = self.post(headers={'Content-Type': 'application/json', 'Transfer-Encoding': 'chunked'})
        self.assertEqual(r.status_code, 400, r.text)

    def test_conflicting_json_fields_do_not_create_challenges(self):
        body = self.body.replace('"operation": "activate"', '"operation":"refresh","operation":"activate"')
        r = self.post(body=body)
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(r.json(), {'error': 'invalid_request'})
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM challenges').fetchone()[0], 0)

    def test_duplicate_content_type_is_rejected(self):
        r = self.post(headers=[('content-type', 'application/json'), ('content-type', 'text/plain')])
        self.assertEqual(r.status_code, 415, r.text)

    def test_valid_request_and_literal_length_keep_working(self):
        r = self.post(headers={'Content-Type': 'application/json; charset=utf-8',
                               'Content-Length': '000' + str(len(self.body))})
        self.assertEqual(r.status_code, 200, r.text)

    def test_deep_json_is_a_bounded_generic_error(self):
        r = self.post(body='[' * 1200 + '0' + ']' * 1200)
        self.assertEqual(r.status_code, 422, r.text)
        self.assertEqual(r.headers['cache-control'], 'no-store')
        self.assertNotIn('Traceback', r.text)

    def test_missing_database_does_not_become_an_empty_healthy_database(self):
        self.path.rename(self.root / 'preserved.db')
        r = self.client.get('/health')
        self.assertEqual(r.status_code, 503, r.text)
        self.assertFalse(self.path.exists(), 'Health check recreated an empty database')
        self.assertEqual(r.json(), {'error': 'service_unavailable'})

    def test_requests_never_recreate_a_missing_database(self):
        self.path.rename(self.root / 'preserved.db')
        r = self.post()
        self.assertEqual(r.status_code, 503, r.text)
        self.assertFalse(self.path.exists(), 'Request recreated an empty database')

    def test_health_requires_usable_authorization_tables(self):
        with self.store.connection() as db:
            db.execute('DROP TABLE challenges')
        r = self.client.get('/health')
        self.assertEqual(r.status_code, 503, r.text)
        self.assertNotIn('challenges', r.text)

    @unittest.skipIf(os.name == 'nt', 'POSIX filesystem policy')
    def test_database_is_private_before_sqlite_opens_it(self):
        candidate = self.root / 'private.db'
        original = sqlite3.connect
        observed = []
        def connect(*args, **kwargs):
            observed.append(candidate.exists() and candidate.stat().st_mode & 0o777 == 0o600)
            return original(*args, **kwargs)
        with patch('service.sqlite3.connect', side_effect=connect):
            LicenseStore(candidate, self.key)
        self.assertTrue(all(observed), 'SQLite was allowed to create a public-permission file')

    @unittest.skipIf(os.name == 'nt', 'POSIX filesystem policy')
    def test_public_database_directory_is_rejected_before_writes(self):
        public = self.root / 'public'
        public.mkdir(mode=0o755)
        with self.assertRaises((ValueError, PermissionError)):
            LicenseStore(public / 'leaky.db', self.key)
        self.assertFalse((public / 'leaky.db').exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink policy')
    def test_database_symlink_is_rejected_without_changing_target(self):
        linked = self.root / 'link.db'
        linked.symlink_to(self.path)
        before = self.path.read_bytes()
        with self.assertRaises((ValueError, PermissionError)):
            LicenseStore(linked, self.key)
        self.assertEqual(self.path.read_bytes(), before)

    @unittest.skipIf(os.name == 'nt', 'POSIX file permission policy')
    def test_public_existing_database_is_rejected_not_silently_chmodded(self):
        self.path.chmod(0o644)
        with self.assertRaises((ValueError, PermissionError)):
            LicenseStore(self.path, self.key)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o644)


if __name__ == '__main__':
    unittest.main()
