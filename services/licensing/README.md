# VYNX managed-service licensing

**Implemented resource:** a per-subscription inventory of enrolled device identities.
This service does **not** license or gate the existing RustDesk peer-to-peer,
rendezvous or hbbr relay protocol. It does not constitute a billing system, a
complete device-management platform or an uncrackable client. Do not sell the
existing relay as access-controlled by this component.

## Trust boundary

The server makes every authorization decision. Editing Flutter UI, setting a
local `premium=true`, extending the phone clock, copying a token to another key,
or replaying a successful signed request does not authorize the managed API.
The client holds its own P-256 signing key, not the service's Ed25519 signing key.
There are no embedded master keys, public admin routes or algorithm negotiation.

Activation codes are 256-bit random values. Only their SHA-256 hashes are stored.
Codes authorize enrollment and must be treated as secrets: a person holding a
code can enroll their own device while seats are available. There is no customer
login or payment verification in this version. Issue codes only after payment is
verified by an operator, not from a client-reported checkout success.

The API requires HTTPS, rate limits per client and globally, bounds request
bodies, rejects extra fields, and does not echo malformed credentials. SQLite
transactions serialize seat allocation and successful challenge consumption.
The signed token is valid for at most five minutes; current server-side license
and device revocation are checked on every managed request. Only activation IDs
are persisted by the Android client; license codes and tokens are not persisted.

Android Keystore keys are non-exportable through the normal API. Hardware-backed
storage depends on the device; this version does not claim verified attestation.
A compromised app/device may still use its key. Play Integrity, certificate
attestation, root detection and anti-debugging are **not** active protections.
Obfuscation only raises inspection cost; it is not authorization or encryption.

## Protocol v1

1. POST `/v1/challenges`: `public_key` (base64 canonical DER SPKI P-256),
   `operation` (`activate`, `refresh`, `devices`), `binding` (lowercase SHA-256 hex
   of the exact activation code, activation ID or token respectively).
2. Sign UTF-8 `VYNXDESK/1\n<operation>\n<challenge>\n<binding>` with
   ECDSA/SHA-256. Send the ASN.1 DER signature as standard base64.
3. POST `/v1/activate` with `code`, `challenge`, `signature`, or `/v1/refresh`
   with `activation_id`, `challenge`, `signature`. Keep only `activation_id`.
4. For inventory, obtain a new `devices` challenge bound to the returned token;
   POST `/v1/managed/devices` with `token`, `challenge`, `signature`.

Challenges expire after 90 seconds and cannot replay a successful operation.
Errors expose stable codes, not internal exceptions. The token is a versioned,
Ed25519-signed service-specific envelope, **not a general JWT**. Other services
must not accept it until an explicit shared contract and server-side adapter are
implemented. The response says `relay_authorization: not-integrated` on purpose.

## Local tests

Requires Python 3.12 or newer. Use a dedicated virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

CI installs the declared production dependency versions separately. The original
local test environment used cryptography 46.0.4; that version is **not** the
production pin and must not be deployed. Tests alone are not a dependency audit.

## Deployment contract (not provisioned automatically)

Create a dedicated `vynx-license` service account. Install code read-only under
`/opt/vynxdesk/licensing`, a virtual environment there, and state under
`/var/lib/vynxdesk-licensing` owned by that account with mode 0700. Never place the
key, live database, SQLite WAL files or activation-code output in Git or an APK.

```sh
umask 077
python service.py init-key /var/lib/vynxdesk-licensing/signing.pem
export VYNX_LICENSE_SIGNING_KEY=/var/lib/vynxdesk-licensing/signing.pem
export VYNX_LICENSE_DB=/var/lib/vynxdesk-licensing/licenses.db
# Set this to the actual exact corresponding source archive you publish:
export VYNX_LICENSE_SOURCE_URL=https://YOUR-SOURCE-HOST/exact-source.zip
uvicorn service:production_app --factory --host 127.0.0.1 --port 8091 \
  --workers 1 --no-access-log --proxy-headers --forwarded-allow-ips=127.0.0.1
```

`YOUR-SOURCE-HOST` is an explicit placeholder, not a configured endpoint. The
production factory fails without its source URL, DB path or private-key path.
Serve the API behind a TLS reverse proxy. Only a trusted local proxy may supply
`X-Forwarded-Proto` and `X-Forwarded-For`; overwrite those headers. Never use
`--forwarded-allow-ips='*'`. Do not expose the Uvicorn port publicly. The provided
systemd/nginx snippets require your actual DNS, TLS paths and source URL.

Use one deployment with a local persistent filesystem; SQLite is not a
multi-region/shared-NFS database. Set trusted server time, request limits and
monitoring. `/health` checks DB access, not key health or end-to-end relay reachability.
`/source` offers the configured source URL. Back up the key and DB securely using
a transactionally consistent SQLite backup; do not copy only a live main DB and
ignore its WAL. A signing-key rotation invalidates existing short-lived tokens;
clients can refresh using their device key and unchanged activation ID.

## Operator commands

Run with the same protected environment and OS account as the service. These are
local CLI operations, **not HTTP endpoints**. Do not paste real license codes
into issue comments, logs, public chat or screenshots.

```sh
python service.py issue --days 30 --max-devices 2
python service.py extend LICENSE_UUID --days 30
python service.py revoke LICENSE_UUID
python service.py rotate-code LICENSE_UUID
python service.py release-device LICENSE_UUID DEVICE_UUID
```

`issue` and `rotate-code` print the enrollment secret exactly once to the operator.
`extend` starts from the later of current expiry and server time; it does not
unrevoke revoked licenses. Revocation is intentionally not reversible via CLI.
`release-device` frees a seat and tombstones the old key, which cannot reenroll
with a retained old code. After a phone reinstall/key loss, identify the customer
outside this API, release the old device, rotate the code and enroll the new key.
Existing valid devices survive code rotation. Formal operator audit logging,
customer authentication, automated payment webhooks and customer support recovery
are pending production requirements, not implicit features.

## Android configuration

Set repository variable `VYNXDESK_SERVICE_API` to the actual HTTPS origin, or build
Flutter with `--dart-define=VYNXDESK_SERVICE_API=https://YOUR-API-HOST`.
No master secret belongs in a dart-define. The service settings tile is absent
when unconfigured, on non-Android platforms, or when accounts/settings are disabled.
The optional service requires Android API 23+; legacy remote desktop remains
unchanged on API 22. The page uses Android Keystore on a background task queue,
refuses HTTP/redirects and persists only an activation ID in no-backup storage.

## License and product constraints

The client and this code remain AGPL-3.0-or-later. Preserve `LICENCE` and `NOTICE`,
ship the exact corresponding source and offer the modified network service's
source to its users. Selling a managed service does not remove recipients'
license rights to modify and redistribute the client. Do not apply a new
closed-source license to RustDesk-derived code. This change does not redefine the
existing VynxDesk Play Bridge SKU or supply a physical USB device.

Reference: https://www.gnu.org/licenses/agpl-3.0.html
Android Keystore: https://developer.android.com/privacy-and-security/keystore
Flutter limitations: https://docs.flutter.dev/deployment/obfuscate

## VYNX integration additions

See `../../ops/vynx/README.md` for vynx.com.tr destinations, private-development/source-distribution boundaries, transactional operator events (`python service.py audit --limit 100`) and online SQLite backups (`python operations.py PRIVATE_DESTINATION.db`). These do not enable paid P2P/relay enforcement or deploy the service.
