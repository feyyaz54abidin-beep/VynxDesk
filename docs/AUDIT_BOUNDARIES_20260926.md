# VynxDesk runtime and release-boundary audit — 2026-09-26

Base: PR #4, commit `58b33df11553b3c92286c27c099bdad4d96d4bf9`.
Scope: managed-license HTTP/storage boundaries, its Flutter client, APK release
validation, Windows publisher policy, and the related tests/build workflows.
This is a focused source review and regression exercise, not an independent
penetration-test certification or a complete review of every upstream line.

## Implemented fixes

### Managed-service input and persistence

- Reject enormous Content-Length values before integer conversion. A 5,000-digit
  value previously returned an uncontrolled HTTP 500; it now returns 413.
- Reject ambiguous duplicate length/content-type headers, conflicting transfer
  framing and duplicate JSON object keys; keep bounded malformed/deep JSON errors
  generic. Handle a disconnected request body without an uncontrolled exception.
- Create SQLite files with private permissions before SQLite can open them.
  Reject an unsafe immediate parent, symlinks, multiple hard links, and public or
  differently owned POSIX database files rather than silently changing ownership
  or permissions. No ACL guarantee is inferred for Windows.
- Open existing runtime connections with URI `mode=rw`. Losing the DB no longer
  silently creates an empty replacement. The constructor can still deliberately
  initialize a new private database; this is not backup recovery.
- `/health` verifies the required authorization/audit schema, not just `SELECT 1`.
  Missing DB/tables return 503 without exposing table names. This is not a full
  integrity check, a write probe, a key-health test, or end-to-end relay readiness.

These HTTP fixtures enter at the ASGI layer. They demonstrate application error
handling, not a proven request-smuggling exploit through a production proxy.
The database filesystem policy assumes trusted ancestor directories and a
protected service OS account; it does not defend against a compromised owner/root.

### Android managed-service client

- Bound responses to 128 KiB so the documented maximum 1,000-device inventory
  works; the old 64-KiB limit rejected a legitimate full-size response.
- Validate canonical activation IDs, service audience, matching refresh identity,
  lease lifetime, device quotas/counts, unique record IDs and safe timestamps
  before persisting activation or handing inventory to the UI.
- Normalize HTTP client failures to `network_unavailable`; keep timeouts distinct
  and do not return transport exception details in user-facing error codes.
- Existing successful mock fixtures now include the fields the real server sends.
  This is response validation, not local cryptographic license enforcement.

### APK release validation

- Require known internal components to explicitly remain non-exported, and the
  input accessibility service to retain the system-only binding permission.
- Check ELF class/machine against the native ABI directory, ELF version and
  shared-object type, segment bounds, power-of-two alignment and offset/address
  congruence. The existing optional 16-KiB release check remains separate.
- Synthetic ELF fixtures now contain realistic required headers. This does not
  certify a shipping APK, its publisher key, Play Integrity or device behavior.

### Windows commercial-release gate

- Validate the configured certificate thumbprint and match signed product
  binaries against that expected publisher even when `-Sign` is not requested.
- A different trusted publisher, missing pin or malformed pin cannot pass the
  signed-product gate. `-AllowUnsigned` only permits genuinely unsigned manual
  test artifacts; it does not permit wrong-publisher or damaged signatures.
- Thumbprints use the existing Windows certificate-store identifier, not a new
  cryptographic signing algorithm. No real publisher certificate is installed.

## Operator impact

Use a dedicated service-owned POSIX directory with mode 0700 and a regular
single-link database file with mode 0600. Existing unsafe deployments now fail
startup intentionally; inspect owner/path and repair deliberately rather than
expecting the application to chmod an arbitrary file. Secure the ancestors too.
When `/health` reports 503 after DB loss, preserve the service state and restore a
verified backup; do not treat a newly created empty database as recovery.

For signed Windows verification, supply `-CertificateThumbprint` or set
`VYNXDESK_SIGNING_CERT_THUMBPRINT` from the intended publisher's trusted identity.
Certificate rotation requires updating that trusted deployment setting. Vendor
DLLs still require valid signatures but are not falsely required to use VYNX's
product certificate. This gate is not a signed update transport.

## Regression evidence and reproducible commands

New test cases: 14 service/storage, 8 APK, 12 Flutter client, 7 publisher cases.
Several tests contain multiple negative samples; these counts are not counts of
independent vulnerabilities.

- Local baseline: 42 service tests and 50 source tests passed before new tests.
- New service fixtures reproduced 12 failures before fixes; new APK fixtures
  reproduced 13 failed assertions/subcases before fixes.
- Pre-fix Flutter run `36218456309`: 89 passed, 10 failed, including the legitimate
  1,000-device response. This is intentional red-phase evidence.
- Pre-fix Windows run `36218770605`: 3 passed, 4 failed in both PowerShell 5.1
  and 7. Signature statuses and metadata are controlled fixtures, not real CAs.
- After source fixes, clean run `36219049294` installed the declared service
  dependencies: 56 service tests and 58 source tests passed; pip-audit reported
  no known vulnerabilities in its 16-package production dependency graph.
- Final current-commit Flutter/Windows results are recorded in the PR and its
  read-only Actions checks. Passing the source suites alone is not their result.

```sh
python -m unittest discover -s services/licensing/tests -v
python -m unittest discover -s scripts/tests -v
python scripts/vynx_brand.py --check
python scripts/check_build_contract.py
python scripts/check_release_contract.py
# Restore the bridge generated from the same source, then:
cd flutter && flutter analyze --no-fatal-warnings --no-fatal-infos
flutter test --reporter expanded
```

On Windows run `scripts/tests/windows/publisher.ps1` and the existing
`distribution.ps1` in both Windows PowerShell 5.1 and PowerShell 7.
The permanent boundary workflow generates the Rust bridge in its own run; it
does not depend on a historic artifact that can expire. The temporary delivery
workflow and encoded patch files are removed from the final tree.

## Unchanged release blockers

Inventory API authorization does not enforce paid P2P/hbbs/hbbr remote sessions.
No payment/refund/recovery integration, desktop license client, app attestation,
signed VYNX updater, production rollout, private repository conversion, physical
Windows/Android/game acceptance, or customer APK/EXE is delivered by this audit.
Legacy/manual update scripts are not approved as a signed auto-update channel.
Existing Flutter warning/info and Rust maintenance/unsound/yanked warnings require
triage; an audit with no known active advisories is not proof of no defects.
Protocol, Rust/native runtime, generated bridge source, legal notices and VYNX
product URLs are not changed by the four runtime-boundary fixes.

An independent reviewer was not available. The patch was self-reviewed for
minimal changes, behavior compatibility and evidence scope; the PR stays draft
until full native/platform and physical acceptance requirements are met.
