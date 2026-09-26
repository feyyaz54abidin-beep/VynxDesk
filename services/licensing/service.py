"""Server-authoritative entitlements for VYNX-managed device inventory.

This service does NOT change or authorize the RustDesk hbbs/hbbr protocol.
License and device private keys never belong in a client binary.
SPDX-License-Identifier: AGPL-3.0-or-later
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from typing import Annotated, Callable, Literal
import uuid
from urllib.parse import urlsplit
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StringConstraints

TOKEN_TTL = 300
CHALLENGE_TTL = 90
AUDIENCE = 'vynxdesk-managed-devices'
MAX_BODY = 16384


class Denied(Exception):
    def __init__(self, status: int = 401, code: str = 'authorization_denied'):
        self.status, self.code = status, code


def sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


def unb64url(value: str) -> bytes:
    if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Invalid encoding')
    return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)


def load_device_key(value: str) -> tuple[bytes, ec.EllipticCurvePublicKey]:
    try:
        der = base64.b64decode(value, validate=True)
        key = serialization.load_der_public_key(der)
        if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError('P-256 required')
        canonical = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        if der != canonical:
            raise ValueError('Noncanonical public key')
        return der, key
    except (ValueError, TypeError, binascii.Error, UnsupportedAlgorithm):
        raise Denied(400, 'invalid_device_key') from None


def prepare_database(path: Path):
    """Create privately before SQLite/WAL opens it; never repair unsafe paths silently."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent = path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode):
        raise ValueError('Database directory must not be a symlink')
    if os.name != 'nt' and (parent.st_mode & 0o077 or parent.st_uid != os.geteuid()):
        raise PermissionError('Database directory must be private and owned by the service account')
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    except FileExistsError:
        pass
    else:
        os.close(descriptor)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('Database must be a regular, single-link private file')
    if os.name != 'nt' and (info.st_mode & 0o077 or info.st_uid != os.geteuid()):
        raise PermissionError('Database file must be private and owned by the service account')


def unique_json_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('Duplicate JSON field')
        result[name] = value
    return result


def reject_json_constant(value):
    raise ValueError('Nonfinite JSON value')


class LicenseStore:
    def __init__(self, database: Path, signing_key: ed25519.Ed25519PrivateKey,
                 *, clock: Callable[[], float] = time.time):
        if not isinstance(signing_key, ed25519.Ed25519PrivateKey):
            raise ValueError('An Ed25519 signing key is required')
        self.database, self.signing_key, self.clock = Path(database).absolute(), signing_key, clock
        prepare_database(self.database)
        self.kid = sha(signing_key.public_key().public_bytes_raw())[:16]
        self.rate_salt = hashlib.sha256(b'VYNXDESK-RATE/1' + signing_key.private_bytes_raw()).digest()
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
              CREATE TABLE IF NOT EXISTS licenses (
                id TEXT PRIMARY KEY, code_hash TEXT UNIQUE NOT NULL,
                expires_at INTEGER NOT NULL, max_devices INTEGER NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0);
              CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY, license_id TEXT NOT NULL REFERENCES licenses(id),
                key_id TEXT NOT NULL, public_key BLOB NOT NULL, activated_at INTEGER NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0, UNIQUE(license_id, key_id));
              CREATE TABLE IF NOT EXISTS challenges (
                nonce TEXT PRIMARY KEY, public_key BLOB NOT NULL, key_id TEXT NOT NULL,
                operation TEXT NOT NULL, binding TEXT NOT NULL, expires_at INTEGER NOT NULL);
              CREATE INDEX IF NOT EXISTS challenge_expiry ON challenges(expires_at);
              CREATE TABLE IF NOT EXISTS operator_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at INTEGER NOT NULL,
                actor TEXT NOT NULL, action TEXT NOT NULL, license_id TEXT NOT NULL,
                device_id TEXT, details TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS request_rates (
                identity TEXT NOT NULL, bucket INTEGER NOT NULL, count INTEGER NOT NULL,
                PRIMARY KEY(identity, bucket));
            ''')

    @contextmanager
    def connection(self, transaction: bool = False):
        db = sqlite3.connect(self.database.as_uri() + '?mode=rw', uri=True, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if transaction:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if transaction:
                db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def now(self) -> int:
        return int(self.clock())

    def _audit(self, db, action: str, license_id: str, *, device_id=None, details=None):
        actor = f'uid:{os.getuid()}' if hasattr(os, 'getuid') else 'local-operator'
        db.execute('INSERT INTO operator_events(occurred_at,actor,action,license_id,device_id,details) VALUES(?,?,?,?,?,?)',
                   (self.now(), actor, action, license_id, device_id,
                    json.dumps(details or {}, sort_keys=True, separators=(',', ':'))))

    def audit_events(self, *, limit: int = 100) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('limit must be 1..1000')
        with self.connection() as db:
            rows = db.execute('SELECT * FROM operator_events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [{**dict(row), 'details': json.loads(row['details'])} for row in rows]

    def issue(self, *, days: int, max_devices: int) -> dict:
        if type(days) is not int or not 1 <= days <= 3650 or type(max_devices) is not int or not 1 <= max_devices <= 1000:
            raise ValueError('days must be 1..3650 and max_devices 1..1000')
        code, lid = 'vxd_' + secrets.token_urlsafe(32), str(uuid.uuid4())
        expiry = self.now() + days * 86400
        with self.connection(True) as db:
            db.execute('INSERT INTO licenses(id,code_hash,expires_at,max_devices) VALUES(?,?,?,?)',
                       (lid, sha(code), expiry, max_devices))
            self._audit(db, 'issue', lid, details={'expires_at': expiry, 'max_devices': max_devices})
        return {'id': lid, 'code': code, 'expires_at': expiry, 'max_devices': max_devices}

    def extend(self, license_id: str, *, days: int) -> int:
        if type(days) is not int or not 1 <= days <= 3650:
            raise ValueError('days must be 1..3650')
        with self.connection(True) as db:
            row = db.execute('SELECT expires_at FROM licenses WHERE id=? AND revoked=0', (license_id,)).fetchone()
            if not row:
                raise ValueError('Unknown or revoked license')
            expiry = max(self.now(), row['expires_at']) + days * 86400
            db.execute('UPDATE licenses SET expires_at=? WHERE id=?', (expiry, license_id))
            self._audit(db, 'extend', license_id, details={'expires_at': expiry, 'days': days})
        return expiry

    def revoke(self, license_id: str):
        with self.connection(True) as db:
            if db.execute('UPDATE licenses SET revoked=1 WHERE id=?', (license_id,)).rowcount != 1:
                raise ValueError('Unknown license')
            self._audit(db, 'revoke', license_id)

    def rotate_code(self, license_id: str) -> str:
        code = 'vxd_' + secrets.token_urlsafe(32)
        with self.connection(True) as db:
            if db.execute('UPDATE licenses SET code_hash=? WHERE id=? AND revoked=0', (sha(code), license_id)).rowcount != 1:
                raise ValueError('Unknown or revoked license')
            self._audit(db, 'rotate-code', license_id)
        return code

    def release_device(self, license_id: str, device_id: str):
        with self.connection(True) as db:
            if db.execute('UPDATE devices SET revoked=1 WHERE id=? AND license_id=?', (device_id, license_id)).rowcount != 1:
                raise ValueError('Unknown device')
            self._audit(db, 'release-device', license_id, device_id=device_id)

    def rate_limit(self, address: str):
        bucket = self.now() // 60
        identity = hmac.new(self.rate_salt, address.encode(), hashlib.sha256).hexdigest()
        limited = False
        with self.connection(True) as db:
            db.execute('DELETE FROM request_rates WHERE bucket<?', (bucket - 1,))
            for key, limit in [(identity, 60), ('global', 600)]:
                db.execute('INSERT INTO request_rates VALUES(?,?,1) ON CONFLICT(identity,bucket) DO UPDATE SET count=MIN(count+1,1000000)',
                           (key, bucket))
                count = db.execute('SELECT count FROM request_rates WHERE identity=? AND bucket=?', (key, bucket)).fetchone()[0]
                limited = limited or count > limit
        if limited:
            raise Denied(429, 'rate_limited')

    def challenge(self, public_key: str, operation: str, binding: str) -> dict:
        der, _ = load_device_key(public_key)
        nonce = secrets.token_urlsafe(32)
        now = self.now()
        with self.connection(True) as db:
            db.execute('DELETE FROM challenges WHERE expires_at<=?', (now,))
            if db.execute('SELECT COUNT(*) FROM challenges').fetchone()[0] >= 2000:
                raise Denied(429, 'challenge_capacity')
            if db.execute('SELECT COUNT(*) FROM challenges WHERE key_id=?', (sha(der),)).fetchone()[0] >= 10:
                raise Denied(429, 'challenge_capacity')
            db.execute('INSERT INTO challenges VALUES(?,?,?,?,?,?)',
                       (nonce, der, sha(der), operation, binding, now + CHALLENGE_TTL))
        return {'challenge': nonce, 'expires_in': CHALLENGE_TTL}

    def _consume(self, db, nonce: str, signature: str, operation: str, binding: str):
        row = db.execute('SELECT * FROM challenges WHERE nonce=?', (nonce,)).fetchone()
        if not row or row['expires_at'] <= self.now() or row['operation'] != operation or row['binding'] != binding:
            raise Denied()
        try:
            key = serialization.load_der_public_key(row['public_key'])
            message = f'VYNXDESK/1\n{operation}\n{nonce}\n{binding}'.encode()
            key.verify(base64.b64decode(signature, validate=True), message, ec.ECDSA(hashes.SHA256()))
        except (ValueError, TypeError, InvalidSignature, binascii.Error):
            raise Denied() from None
        db.execute('DELETE FROM challenges WHERE nonce=?', (nonce,))
        return row

    def _license(self, db, lid: str):
        row = db.execute('SELECT * FROM licenses WHERE id=?', (lid,)).fetchone()
        if not row or row['revoked'] or row['expires_at'] <= self.now():
            raise Denied()
        return row

    def _mint(self, license, device) -> dict:
        now = self.now()
        expiry = min(now + TOKEN_TTL, license['expires_at'])
        payload = {'aud': AUDIENCE, 'license_id': license['id'], 'activation_id': device['id'],
                   'key_id': device['key_id'], 'iat': now, 'exp': expiry}
        encoded = b64url(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode())
        message = f'v1.{self.kid}.{encoded}'
        signature = self.signing_key.sign(b'VYNXDESK-TOKEN/1\n' + message.encode())
        return {'token': message + '.' + b64url(signature), 'activation_id': device['id'],
                'expires_in': expiry - now, 'service': AUDIENCE}

    def activate(self, code: str, challenge: str, signature: str) -> dict:
        with self.connection(True) as db:
            proof = self._consume(db, challenge, signature, 'activate', sha(code))
            license = db.execute('SELECT * FROM licenses WHERE code_hash=?', (sha(code),)).fetchone()
            if not license:
                raise Denied()
            license = self._license(db, license['id'])
            device = db.execute('SELECT * FROM devices WHERE license_id=? AND key_id=?',
                                (license['id'], proof['key_id'])).fetchone()
            if device and device['revoked']:
                raise Denied()
            if not device:
                count = db.execute('SELECT COUNT(*) FROM devices WHERE license_id=? AND revoked=0', (license['id'],)).fetchone()[0]
                if count >= license['max_devices']:
                    raise Denied(409, 'device_limit_reached')
                did = str(uuid.uuid4())
                db.execute('INSERT INTO devices(id,license_id,key_id,public_key,activated_at) VALUES(?,?,?,?,?)',
                           (did, license['id'], proof['key_id'], proof['public_key'], self.now()))
                device = db.execute('SELECT * FROM devices WHERE id=?', (did,)).fetchone()
            return self._mint(license, device)

    def refresh(self, activation_id: str, challenge: str, signature: str) -> dict:
        with self.connection(True) as db:
            proof = self._consume(db, challenge, signature, 'refresh', sha(activation_id))
            device = db.execute('SELECT * FROM devices WHERE id=?', (activation_id,)).fetchone()
            if not device or device['revoked'] or device['key_id'] != proof['key_id']:
                raise Denied()
            return self._mint(self._license(db, device['license_id']), device)

    def _verify_token(self, token: str) -> dict:
        try:
            version, kid, encoded, signature = token.split('.')
            if version != 'v1' or kid != self.kid:
                raise ValueError()
            self.signing_key.public_key().verify(unb64url(signature),
                b'VYNXDESK-TOKEN/1\n' + f'{version}.{kid}.{encoded}'.encode())
            payload = json.loads(unb64url(encoded))
            if not isinstance(payload, dict) or set(payload) != {'aud', 'license_id', 'activation_id', 'key_id', 'iat', 'exp'}:
                raise ValueError()
            if payload['aud'] != AUDIENCE or type(payload['exp']) is not int or type(payload['iat']) is not int:
                raise ValueError()
            now = self.now()
            if payload['exp'] <= now or payload['iat'] > now + 5 or not 0 < payload['exp'] - payload['iat'] <= TOKEN_TTL:
                raise ValueError()
            if any(not isinstance(payload[k], str) for k in ('license_id', 'activation_id', 'key_id')):
                raise ValueError()
            return payload
        except (ValueError, TypeError, InvalidSignature, KeyError, binascii.Error, UnicodeDecodeError):
            raise Denied() from None

    def devices(self, token: str, challenge: str, signature: str) -> dict:
        payload = self._verify_token(token)
        with self.connection(True) as db:
            if payload['exp'] <= self.now():
                raise Denied()
            proof = self._consume(db, challenge, signature, 'devices', sha(token))
            if proof['key_id'] != payload['key_id']:
                raise Denied()
            license = self._license(db, payload['license_id'])
            device = db.execute('SELECT * FROM devices WHERE id=? AND license_id=?',
                                (payload['activation_id'], license['id'])).fetchone()
            if not device or device['revoked'] or device['key_id'] != proof['key_id']:
                raise Denied()
            rows = db.execute('SELECT id,activated_at FROM devices WHERE license_id=? AND revoked=0 ORDER BY activated_at,id',
                              (license['id'],)).fetchall()
            return {'devices': [dict(row) for row in rows], 'max_devices': license['max_devices'],
                    'expires_at': license['expires_at'], 'service': AUDIENCE,
                    'relay_authorization': 'not-integrated'}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ChallengeInput(StrictModel):
    public_key: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    operation: Literal['activate', 'refresh', 'devices']
    binding: Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{64}$')]


class Proof(StrictModel):
    challenge: Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9_-]{43}$')]
    signature: Annotated[str, StringConstraints(min_length=1, max_length=144)]


class ActivationInput(Proof):
    code: Annotated[str, StringConstraints(pattern=r'^vxd_[A-Za-z0-9_-]{43}$')]


class RefreshInput(Proof):
    activation_id: Annotated[str, StringConstraints(pattern=r'^[a-f0-9-]{36}$')]


class DeviceInput(Proof):
    token: Annotated[str, StringConstraints(min_length=1, max_length=4096)]


def create_app(store: LicenseStore, *, source_url: str | None = None) -> FastAPI:
    if source_url is not None:
        url = urlsplit(source_url)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
            raise ValueError('Exact source must have a public HTTPS URL')
    app = FastAPI(title='VynxDesk managed licensing', docs_url=None, redoc_url=None, openapi_url=None)

    def error(status: int, code: str):
        headers = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}
        if status == 429:
            headers['Retry-After'] = '60'
        return JSONResponse({'error': code}, status_code=status, headers=headers)

    @app.exception_handler(Denied)
    async def denied_handler(request, exc):
        return error(exc.status, exc.code)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, exc):
        # Pydantic's default response echoes invalid inputs, including license codes.
        return error(422, 'invalid_request')

    @app.middleware('http')
    async def security(request: Request, call_next):
        if request.scope.get('path', '').startswith('/v1/'):
            if request.scope.get('scheme') != 'https':
                return error(400, 'https_required')
            try:
                await run_in_threadpool(store.rate_limit, request.client.host if request.client else 'unknown')
            except Denied as exc:
                return error(exc.status, exc.code)
            except sqlite3.Error:
                return error(503, 'service_unavailable')
            if request.method == 'POST':
                lengths = request.headers.getlist('content-length')
                if not lengths:
                    return error(411, 'content_length_required')
                if len(lengths) != 1 or 'transfer-encoding' in request.headers:
                    return error(400, 'invalid_content_length')
                length = lengths[0]
                if not re.fullmatch(r'[0-9]+', length):
                    return error(400, 'invalid_content_length')
                # Bound before int(): thousands of digits otherwise raise ValueError.
                length = length.lstrip('0') or '0'
                if len(length) > len(str(MAX_BODY)) or int(length) > MAX_BODY:
                    return error(413, 'request_too_large')
                content_types = request.headers.getlist('content-type')
                if len(content_types) != 1 or content_types[0].split(';')[0].strip().lower() != 'application/json':
                    return error(415, 'json_required')
                body = bytearray()
                try:
                    async with asyncio.timeout(10):
                        async for chunk in request.stream():
                            if len(body) + len(chunk) > MAX_BODY:
                                return error(413, 'request_too_large')
                            body.extend(chunk)
                except TimeoutError:
                    return error(408, 'request_timeout')
                except ClientDisconnect:
                    return error(400, 'incomplete_request')
                if len(body) != int(length):
                    return error(400, 'invalid_content_length')
                try:
                    decoded = json.loads(body, object_pairs_hook=unique_json_object,
                                         parse_constant=reject_json_constant)
                    if not isinstance(decoded, dict):
                        raise ValueError('Object required')
                except (ValueError, RecursionError):
                    return error(422, 'invalid_request')
                # Starlette's cached request replays this body to the ASGI router.
                request._body = bytes(body)
        try:
            response = await call_next(request)
        except sqlite3.Error:
            return error(503, 'service_unavailable')
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/source')
    def source():
        if source_url is None:
            raise Denied(503, 'source_offer_not_configured')
        return {'license': 'AGPL-3.0-or-later', 'url': source_url}

    @app.get('/health')
    def health():
        with store.connection() as db:
            for query in (
                'SELECT id,code_hash,expires_at,max_devices,revoked FROM licenses LIMIT 0',
                'SELECT id,license_id,key_id,public_key,activated_at,revoked FROM devices LIMIT 0',
                'SELECT nonce,public_key,key_id,operation,binding,expires_at FROM challenges LIMIT 0',
                'SELECT identity,bucket,count FROM request_rates LIMIT 0',
                'SELECT id,occurred_at,actor,action,license_id,device_id,details FROM operator_events LIMIT 0',
            ):
                db.execute(query).fetchall()
        return {'status': 'ok', 'service': AUDIENCE}

    @app.post('/v1/challenges')
    def challenges(data: ChallengeInput):
        return store.challenge(**data.model_dump())

    @app.post('/v1/activate')
    def activate(data: ActivationInput):
        return store.activate(**data.model_dump())

    @app.post('/v1/refresh')
    def refresh(data: RefreshInput):
        return store.refresh(**data.model_dump())

    @app.post('/v1/managed/devices')
    def devices(data: DeviceInput):
        return store.devices(**data.model_dump())

    return app


def load_store() -> LicenseStore:
    key_path = Path(os.environ['VYNX_LICENSE_SIGNING_KEY'])
    if os.name != 'nt' and key_path.stat().st_mode & 0o077:
        raise ValueError('Signing key file must not be group/world-readable')
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    return LicenseStore(Path(os.environ['VYNX_LICENSE_DB']), key)


def production_app() -> FastAPI:
    return create_app(load_store(), source_url=os.environ['VYNX_LICENSE_SOURCE_URL'])


def main():
    parser = argparse.ArgumentParser(description='Offline operator CLI; no public admin endpoint')
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init-key')
    init.add_argument('path', type=Path)
    issue = sub.add_parser('issue')
    issue.add_argument('--days', required=True, type=int)
    issue.add_argument('--max-devices', required=True, type=int)
    extend = sub.add_parser('extend')
    extend.add_argument('license_id')
    extend.add_argument('--days', required=True, type=int)
    revoke = sub.add_parser('revoke')
    revoke.add_argument('license_id')
    rotate = sub.add_parser('rotate-code')
    rotate.add_argument('license_id')
    release = sub.add_parser('release-device')
    release.add_argument('license_id')
    release.add_argument('device_id')
    audit = sub.add_parser('audit')
    audit.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    if args.command == 'init-key':
        pem = ed25519.Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        fd = os.open(args.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as output:
            output.write(pem)
        print('Signing key created; keep it outside the repository and back it up securely.')
        return
    store = load_store()
    if args.command == 'issue':
        print(json.dumps(store.issue(days=args.days, max_devices=args.max_devices)))
    elif args.command == 'extend':
        print(json.dumps({'expires_at': store.extend(args.license_id, days=args.days)}))
    elif args.command == 'revoke':
        store.revoke(args.license_id)
    elif args.command == 'rotate-code':
        print(json.dumps({'code': store.rotate_code(args.license_id)}))
    elif args.command == 'audit':
        print(json.dumps(store.audit_events(limit=args.limit)))
    else:
        store.release_device(args.license_id, args.device_id)


if __name__ == '__main__':
    main()
