import base64
import concurrent.futures
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class LicensingTests(unittest.TestCase):
    def setUp(self):
        from service import LicenseStore, create_app
        self.temp = tempfile.TemporaryDirectory()
        self.now = [1_800_000_000]
        self.key = ed25519.Ed25519PrivateKey.generate()
        self.store = LicenseStore(Path(self.temp.name) / 'licenses.db', self.key, clock=lambda: self.now[0])
        self.app = create_app(self.store)
        self.client = TestClient(self.app, base_url='https://service.test')
        self.device = ec.generate_private_key(ec.SECP256R1())
        self.license = self.store.issue(days=30, max_devices=2)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def pub(self, key=None):
        return base64.b64encode((key or self.device).public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()

    def proof(self, operation, value, key=None, client=None):
        key = key or self.device
        client = client or self.client
        binding = hashlib.sha256(value.encode()).hexdigest()
        r = client.post('/v1/challenges', json={'public_key': self.pub(key), 'operation': operation, 'binding': binding})
        self.assertEqual(r.status_code, 200, r.text)
        challenge = r.json()['challenge']
        message = f'VYNXDESK/1\n{operation}\n{challenge}\n{binding}'.encode()
        signature = base64.b64encode(key.sign(message, ec.ECDSA(hashes.SHA256()))).decode()
        return {'challenge': challenge, 'signature': signature}

    def activate(self, key=None, code=None, client=None):
        code = code or self.license['code']
        client = client or self.client
        return client.post('/v1/activate', json={'code': code, **self.proof('activate', code, key, client)})

    def inventory(self, token, key=None, client=None):
        client = client or self.client
        return client.post('/v1/managed/devices', json={'token': token, **self.proof('devices', token, key, client)})

    def test_activate_and_server_protected_inventory(self):
        r = self.activate()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['expires_in'], 300)
        inv = self.inventory(r.json()['token'])
        self.assertEqual(inv.status_code, 200, inv.text)
        self.assertEqual(len(inv.json()['devices']), 1)
        self.assertNotIn('code', inv.text)
        self.assertNotIn('public_key', inv.text)

    def test_activation_replay_rejected(self):
        code = self.license['code']
        data = {'code': code, **self.proof('activate', code)}
        self.assertEqual(self.client.post('/v1/activate', json=data).status_code, 200)
        self.assertEqual(self.client.post('/v1/activate', json=data).status_code, 401)

    def test_managed_request_replay_rejected(self):
        token = self.activate().json()['token']
        data = {'token': token, **self.proof('devices', token)}
        self.assertEqual(self.client.post('/v1/managed/devices', json=data).status_code, 200)
        self.assertEqual(self.client.post('/v1/managed/devices', json=data).status_code, 401)

    def test_wrong_device_cannot_copy_token(self):
        token = self.activate().json()['token']
        other = ec.generate_private_key(ec.SECP256R1())
        self.assertEqual(self.inventory(token, other).status_code, 401)

    def test_token_payload_change_rejected(self):
        token = self.activate().json()['token']
        parts = token.split('.')
        payload = json.loads(base64.urlsafe_b64decode(parts[2] + '=' * (-len(parts[2]) % 4)))
        payload['exp'] += 100000
        parts[2] = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        self.assertEqual(self.inventory('.'.join(parts)).status_code, 401)

    def test_unknown_signer_rejected(self):
        token = self.activate().json()['token']
        parts = token.split('.')
        parts[1] = 'unknown'
        self.assertEqual(self.inventory('.'.join(parts)).status_code, 401)

    def test_malformed_token_rejected_without_server_error(self):
        for token in ['none', 'v1.x.!.!', 'v1.x.e30.AA']:
            self.assertEqual(self.inventory(token).status_code, 401)

    def test_expired_token_rejected(self):
        token = self.activate().json()['token']
        self.now[0] += 301
        self.assertEqual(self.inventory(token).status_code, 401)

    def test_revocation_invalidates_already_signed_token(self):
        token = self.activate().json()['token']
        self.store.revoke(self.license['id'])
        self.assertEqual(self.inventory(token).status_code, 401)

    def test_revoked_device_cannot_refresh(self):
        data = self.activate().json()
        self.store.release_device(self.license['id'], data['activation_id'])
        r = self.client.post('/v1/refresh', json={'activation_id': data['activation_id'], **self.proof('refresh', data['activation_id'])})
        self.assertEqual(r.status_code, 401)

    def test_device_can_refresh_without_storing_activation_code(self):
        data = self.activate().json()
        self.now[0] += 301
        r = self.client.post('/v1/refresh', json={'activation_id': data['activation_id'], **self.proof('refresh', data['activation_id'])})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.inventory(r.json()['token']).status_code, 200)

    def test_same_device_does_not_consume_extra_seat(self):
        a = self.activate().json()
        b = self.activate().json()
        self.assertEqual(a['activation_id'], b['activation_id'])
        self.assertEqual(len(self.inventory(b['token']).json()['devices']), 1)

    def test_seat_limit_transactional_under_concurrency(self):
        license = self.store.issue(days=1, max_devices=1)
        def attempt(_):
            with TestClient(self.app, base_url='https://service.test') as client:
                return self.activate(ec.generate_private_key(ec.SECP256R1()), license['code'], client).status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(4)))
        self.assertEqual(results.count(200), 1, results)
        self.assertEqual(results.count(409), 3, results)

    def test_inventory_never_crosses_license_boundary(self):
        other = self.store.issue(days=1, max_devices=1)
        self.activate(ec.generate_private_key(ec.SECP256R1()), other['code'])
        token = self.activate().json()['token']
        self.assertEqual(len(self.inventory(token).json()['devices']), 1)

    def test_challenge_expires(self):
        code = self.license['code']
        data = {'code': code, **self.proof('activate', code)}
        self.now[0] += 91
        self.assertEqual(self.client.post('/v1/activate', json=data).status_code, 401)

    def test_challenge_purpose_is_bound(self):
        code = self.license['code']
        data = {'code': code, **self.proof('refresh', code)}
        self.assertEqual(self.client.post('/v1/activate', json=data).status_code, 401)

    def test_license_expiry_is_server_authoritative(self):
        data = self.activate().json()
        self.now[0] += 31 * 86400
        r = self.client.post('/v1/refresh', json={'activation_id': data['activation_id'], **self.proof('refresh', data['activation_id'])})
        self.assertEqual(r.status_code, 401)

    def test_expiry_capped_at_license_expiry(self):
        self.now[0] = self.license['expires_at'] - 10
        self.assertEqual(self.activate().json()['expires_in'], 10)

    def test_storage_contains_no_plaintext_license_code(self):
        self.activate()
        with self.store.connection() as db:
            dump = '\n'.join(db.iterdump())
        self.assertNotIn(self.license['code'], dump)

    def test_restart_preserves_devices_and_revocations(self):
        from service import LicenseStore, create_app
        token = self.activate().json()['token']
        self.store.revoke(self.license['id'])
        other = LicenseStore(self.store.database, self.key, clock=lambda: self.now[0])
        with TestClient(create_app(other), base_url='https://service.test') as client:
            self.assertEqual(self.inventory(token, client=client).status_code, 401)

    def test_no_public_provisioning_route(self):
        self.assertEqual(self.client.post('/v1/admin/issue', json={}).status_code, 404)

    def test_malformed_host_cannot_bypass_https_policy(self):
        insecure = TestClient(self.app, base_url='http://service.test')
        try:
            for host in ['service.test/not-v1#', 'service.test/?x=', 'service.test@other.test/']:
                response = insecure.post('/v1/challenges', headers={'Host': host}, json={
                    'public_key': self.pub(), 'operation': 'activate', 'binding': 'a' * 64})
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(response.json().get('error'), 'https_required')
        finally:
            insecure.close()

    def test_no_plain_http_for_credentials(self):
        with TestClient(self.app, base_url='http://service.test') as client:
            r = client.post('/v1/challenges', json={})
            self.assertEqual(r.status_code, 400)

    def test_rate_limit_is_enforced(self):
        results = [self.client.post('/v1/challenges', json={}).status_code for _ in range(65)]
        self.assertIn(429, results)

    def test_no_secret_in_error_response(self):
        r = self.activate(code='vxd_' + 'X' * 43)
        self.assertEqual(r.status_code, 401)
        self.assertNotIn('XXXX', r.text)
        self.assertNotIn('Traceback', r.text)

    def test_invalid_key_and_unknown_fields_rejected(self):
        r = self.client.post('/v1/challenges', json={'public_key': 'bad', 'operation': 'activate', 'binding': 'a' * 64})
        self.assertEqual(r.status_code, 400)
        r = self.client.post('/v1/challenges', json={'public_key': self.pub(), 'operation': 'activate', 'binding': 'a' * 64, 'premium': True})
        self.assertEqual(r.status_code, 422)

    def test_no_cache_headers(self):
        r = self.activate()
        self.assertEqual(r.headers['cache-control'], 'no-store')

    def test_renewal_preserves_device_but_revoked_license_cannot_renew(self):
        data = self.activate().json()
        expiry = self.store.extend(self.license['id'], days=7)
        self.assertEqual(expiry, self.license['expires_at'] + 7 * 86400)
        self.assertEqual(self.inventory(data['token']).status_code, 200)
        self.store.revoke(self.license['id'])
        with self.assertRaises(ValueError):
            self.store.extend(self.license['id'], days=7)

    def test_rotation_rejects_old_code_without_breaking_existing_device(self):
        data = self.activate().json()
        code = self.store.rotate_code(self.license['id'])
        other = ec.generate_private_key(ec.SECP256R1())
        self.assertEqual(self.activate(other).status_code, 401)
        self.assertEqual(self.activate(other, code).status_code, 200)
        self.assertEqual(self.inventory(data['token']).status_code, 200)

    def test_revoked_device_tombstone_cannot_reenroll_with_old_code(self):
        data = self.activate().json()
        self.store.release_device(self.license['id'], data['activation_id'])
        self.assertEqual(self.activate().status_code, 401)
        self.assertEqual(self.inventory(data['token']).status_code, 401)

    def test_request_body_limits_and_generic_validation(self):
        r = self.client.post('/v1/activate', content='x' * 16385,
                             headers={'Content-Type': 'application/json'})
        self.assertEqual(r.status_code, 413)
        r = self.client.post('/v1/activate', content=self.license['code'],
                             headers={'Content-Type': 'application/json'})
        self.assertEqual(r.status_code, 422)
        self.assertNotIn(self.license['code'], r.text)
        self.assertEqual(self.client.post('/v1/activate', content='hi').status_code, 415)

    def test_other_elliptic_curve_is_rejected(self):
        other = ec.generate_private_key(ec.SECP384R1())
        r = self.client.post('/v1/challenges', json={'public_key': self.pub(other),
            'operation': 'activate', 'binding': 'a' * 64})
        self.assertEqual(r.status_code, 400)

    def test_source_offer_is_configured_and_does_not_leak_internal_path(self):
        from service import create_app
        with TestClient(create_app(self.store, source_url='https://source.test/exact.zip'),
                        base_url='https://service.test') as client:
            r = client.get('/source')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()['url'], 'https://source.test/exact.zip')
            self.assertNotIn(self.temp.name, r.text)
        with self.assertRaises(ValueError):
            create_app(self.store, source_url='http://source.test/unsafe.zip')


if __name__ == '__main__':
    unittest.main()
