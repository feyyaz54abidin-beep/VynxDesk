# Android / managed-service security readiness

## Source findings corrected

- Release manifest included a custom DEBUG_BOOT_COMPLETED action while the boot
  receiver accepted it without a debug-build guard. The action is now debug-only,
  with a BuildConfig.DEBUG runtime condition as well.
- Android backup was enabled for a remote-access application. Full backup and
  modern cloud/device-transfer rules now exclude app data. This is not protection
  against root, screenshots, process compromise or every OEM implementation.
- A permission activity and floating-window service had no explicit exported=false.
- APK pipelines could publish a debug-signed build labelled "unsigned". Customer
  upload/publication now requires the explicit expected publisher SHA-256
  certificate, a verified v2+ signature, the correct app ID, no debug/test flags,
  no custom debug boot action, required native libraries and 16 KB ELF/ZIP checks.
- Release Flutter APK commands enable symbol obfuscation; separate symbol maps
  are retained as CI artifacts for 30 days (do not treat public-repo artifacts as
  a secret store). Archive maps securely for the supported release lifetime.

## Dependency audit follow-up

The clean-runner audit rejected Starlette 0.50.0 (ten advisory records covering
five distinct PYSEC IDs). Upgrade the isolated service to FastAPI 0.141.1 and
Starlette 1.7.0; keep the audit as a blocking gate. Security middleware uses the
ASGI scope path/scheme, not a URL reconstructed from the untrusted Host header.
A regression test first reproduced a malformed Host bypass of the HTTPS policy
on the old dependency stack. It now returns https_required before dispatch.

## Actual paid-service boundary

`services/licensing` protects enrolled-device inventory with server checks. The
Android settings page uses its own Keystore P-256 identity. This is **not** a
license gate on peer-to-peer or hbbr remote-desktop traffic. A patched client
cannot mint a valid managed-service token or use another device's token without
its proof key, but the service does not attest the client binary. Code holders
can enroll seats using another compatible client. See the service README.

No Play Integrity verdict validation, payment provider webhook, customer login,
relay authorization adapter, enforced cloud-session quota or desktop licensing
client is claimed by this change. Real games and physical USB input are outside
these Android/security tests; prior Windows work does not prove their acceptance.

## Required before a customer release

1. Deploy the managed service with protected key/database, trusted TLS proxy and
   actual exact source URL. Configure its real HTTPS API origin.
2. Provision the Android publisher keystore and expected certificate fingerprint
   `VYNXDESK_ANDROID_CERT_SHA256`; never accept a debug certificate for a release.
3. Keep production rendezvous identity checks; missing production host/public key
   remain a release failure, not a reason to publish a public-debug build.
4. Build and inspect the exact final APK using `scripts/check_android_apk.py` with
   `--fingerprint EXPECTED_SHA256 --require-16kb`. The native ELF and zipalign tests
   are evidence about layout, not proof of functional 16 KB device support.
5. Run clean install/update, Android 23 and recent Android device acceptance,
   screen-capture/accessibility consent, background-service, reconnect and
   clipboard/file-transfer tests. Test enrollment, expiry/revocation, offline
   behavior, reinstall recovery and Keystore failure on real devices.
6. Run current dependency audits and full Flutter/native CI. Local tests alone
   do not certify dependency safety or Android/Kotlin compilation.
7. Complete payment verification/refunds/recovery, operations monitoring,
   operator audit logs, service terms/privacy/source offer and server-side
   enforcement for every paid service before marketing that service.

## Reproduce checks

```sh
python -m unittest discover -s scripts/tests -v
python -m unittest discover -s services/licensing/tests -v
cd flutter && flutter test test/service_license_client_test.dart
```

Reference sources consulted September 26, 2026:
- https://developer.android.com/privacy-and-security/keystore
- https://developer.android.com/identity/data/autobackup
- https://developer.android.com/guide/practices/page-sizes
- https://developer.android.com/google/play/integrity/verdicts
- https://docs.flutter.dev/deployment/obfuscate
- https://cryptography.io/en/latest/changelog/
- https://www.gnu.org/licenses/agpl-3.0.html
