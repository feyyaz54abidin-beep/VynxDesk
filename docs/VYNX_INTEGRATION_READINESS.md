# VYNX integration verification — 2026-09-26

## Delivered scope

This integration combines the Android/managed-inventory code from PR #2
(c0574bc05d49d74a862fd951d7badacb0738664c), the verified ringbuf remediation from
PR #3, and VYNX-specific product links, deployment examples, an operator journal
and a consistent private database backup utility. It incorporates PR #1 through
PR #2. No master merge or repository visibility change is performed.

Product links use https://vynx.com.tr/vynxdesk/ and a generated, validated brand
profile. The existing main BOT/AIO website is not modified. The prepared API and
relay hostnames are desk-api.vynx.com.tr and desk-relay.vynx.com.tr; these are
planned configuration, not verified DNS/TLS deployments. Source and publisher
credentials are deliberately not fabricated or committed.

The old unconfigured account API fallback admin.vynxdesk.com is removed. Explicit
compatible self-host settings remain unchanged; the managed inventory API must
not receive the unrelated account-login protocol. VynxDesk-branded automatic
RustDesk version checks are disabled before their fingerprint-bearing request.
A VYNX signed update feed is still not implemented.

## Exact clean-runner evidence

- Run: https://github.com/feyyaz54abidin-beep/VynxDesk/actions/runs/36215314873
- Tested code commit: c29e43687b086235f3c76d32fd3168ddf0f53944
- Tested tree including the temporary workflow: 78f73f799ed62c144096ee4b7fbf07f15f598ae0
- Normalized product tree without that workflow: 9a424f44562f40dd4bd92670825dccd9b3b319ed
- The normalized tree exactly matches the locally reviewed candidate.
- Artifact: vynxdesk-integration-evidence (10897495993)
- Artifact SHA-256: 4c9de0c17acef21e20d43a796509b277c799d9cedd681fd7d074afc64aafccb9

Results observed on the combined candidate:

| Verification | Observed result |
|---|---|
| Managed service and operator/backup tests | 42 passed |
| Python source, Android packaging and brand contracts | 50 passed |
| Complete existing Flutter test suite plus brand tests | 87 passed |
| Actual AudioBuffer source / ringbuf regression probe | 5 passed |
| Actual Rust service-domain classifier probe | 2 passed |
| Flutter analysis | No errors; 246 existing warning/info diagnostics remain |
| Production Python dependency graph | 16 resolved packages; no known vulnerabilities reported |
| Root cargo audit | Zero active vulnerabilities; 19 unmaintained, 2 unsound and 1 yanked-package warnings remain |
| Build/release source contracts | Passed |

New audit/backup/brand failures were observed locally before implementation.
The clean runner installed the declared production service versions rather than
relying on the different preinstalled local Python environment. The audio and
domain probes compile extracted production implementations, but are not a full
native client build or a physical-device test. No full-build claim is inferred
from these probes. Prior PR #2 and #3 Full Flutter CI runs passed separately;
that is not a substitute for platform CI on this combined candidate.

The initial transport workflow had a YAML scalar quoting error and did not
execute code; it was corrected before the successful run above. The final tree
removes that temporary write-enabled workflow and its transport files. The new
permanent brand/operations workflow is read-only and never publishes or pushes.
Final follow-up changes are documentation and CI only; tested runtime code is
unchanged. No independent reviewer was available; the changes were self-reviewed
and checked for unnecessary changes to existing paths.

## Regression surface

- src/common.rs: branded updater early returns, unconfigured compatible-account
  fallback, service-domain classification and its unit test. Transport/session
  authentication is unchanged.
- Six desktop/mobile Flutter page files: thin imports and product-navigation URL
  substitutions. Source/attribution and technical upstream references remain.
- src/ui/install.tis and two Linux metadata files: product privacy link and
  displayed name/description only. Internal service and application IDs remain.
- services/licensing/service.py: additive operator-events table; an event in the
  same transaction as each successful operator mutation; local audit CLI.
  Audit-write failure rolls back the mutation. Public API authorization and its
  existing entitlement boundary remain unchanged.
- services/licensing/operations.py: new offline SQLite online-backup command;
  committed WAL content is included, no overwrite, private POSIX destination,
  integrity check and SHA-256 output. Not a remote administration endpoint.
- Cargo.toml, Cargo.lock and src/client.rs carry the exact earlier ringbuf
  migration; the associated dependency-edge changes are described in
  docs/RINGBUF_SECURITY.md. No additional submodule or generated FFI change.

The local operator journal identifies an OS process account, not an authenticated
human, and is not tamper-proof against the database administrator. Backups and
signing keys are confidential operational assets, never website/source content.

## Customer-release hold

The prepared static product/privacy pages are noindex release drafts, without
payment or APK/EXE links. They are not deployed. Privacy controller/contact,
retention, processing/transfer details and review are still required.

The managed entitlement protects only the implemented enrolled-device inventory
API. It does not license or enforce the existing P2P/hbbs/hbbr session traffic.
Payment/refund reconciliation, customer identity/recovery, a licensed relay
adapter, desktop licensing, app attestation and a signed VYNX update channel
remain separate work. There is no uncrackability or game-compatibility guarantee.

Full combined native/platform CI, real Windows/Android acceptance, actual
publisher certificates, DNS/TLS/relay and service deployment, protected backups
and restore drills, and published corresponding source are required before a
customer release. No shipping APK/EXE was produced or inspected in this change.
Private development does not remove source/modification/redistribution rights
for AGPL-covered components; see ops/vynx/README.md for the source handoff.
