# Connection Doctor verification — 2026-09-26

## Delivery and scope

Base: PR #5, `d277974ba04dd3547a28e7d3243eaf89593e23ca`.
Feature branch: `codex/vynxdesk-connection-doctor-20260926`.
The user delegated feature choice after reviewing proposals. The selected bounded
feature is a local, read-only Connection Doctor on the existing Connection Insight
observer. Control Deck, Device Wall and new remote operations are not included.

Entry: open an existing remote session, enable **Show quality monitor**, then
select **Connection doctor** (**Bağlantı tanılama** in Turkish). The existing
shared overlay/session dialog is used on mobile and desktop. See
`CONNECTION_DOCTOR.md` for observation thresholds, privacy and limitations.

## Evidence actually executed

| Check | Observed result |
| --- | --- |
| Before implementation, focused classifier run 36223217818 | 5 passed, 14 intentional assertion failures |
| Implemented feature, isolated run 36224426989 | 30 passed: 20 classifier/privacy and 10 widget tests |
| Final full Flutter suite, run 36224763610 | 129 passed, including those 30 feature tests |
| Final source/APK/brand/locale suite, same run | 62 passed, including 4 new feature contracts |
| Full Flutter analysis, same run | No errors; 247 pre-existing warning/information diagnostics remain |
| New feature and its tests in full project analysis | No diagnostic names the feature or its test files |
| Formatting, build/release contracts and VYNX links | Passed |

The final run first applied only two exact brace/style corrections to the already
verified runtime code, then ran analysis and tests and committed the tested tree.
Its tested commit is `94876661cfd7630e038064c5506948660e4fc9b2`.
Its tree is `2e436ef09f3d214a06fce327a065285db62beb49`.
After removing both temporary workflows, the product tree is
`996ab59d82c98d3f8275f44c02475176641be69e`, exactly matching the local reviewed tree.
The final follow-up adds only this evidence document and read-only permanent CI.
Tested application code, tests and translations are unchanged in that follow-up.

Final-run artifact: `10900750974`, `vynxdesk-doctor-final-evidence`.
Archive SHA-256: `f25aec2fa85ae2d911274dede890bf669df348a549a154868dcb4381262fed50`.
Prior green artifact: `10900221373`; red artifact: `10899632581`.
Downloaded logs were read and archive hashes verified before recording results.
Run: https://github.com/feyyaz54abidin-beep/VynxDesk/actions/runs/36224763610

The full Flutter runs reused the generated bridge artifact from run 36223925498
for the unchanged native API; this was not a bridge generated in the final run.
Native API/dependency equivalence was checked. The permanent focused workflow
uses actual feature source without a bridge and does not depend on that historic
artifact. Existing full-platform CI remains the native integration/build gate.

## What the tests cover

Classifier cases include missing/unknown/malformed telemetry, receipt freshness,
reconnect/reset, security state, view-only and keyboard permission observations,
relay routing, latency and frame-rate advisories, bounded numbers and frame maps,
immutable reports and exclusion of arbitrary/free-form fields from JSON.

Widget cases cover explicit frozen preview and copy, clipboard failure, narrow
viewport and large text, pending-copy disposal, listener/timer cleanup and
preventing duplicate dialogs. Source contracts verify the two existing entry
hooks, allowed dependencies and localization completeness. Source contracts are
not full session/native-input integration tests.

During development the first candidate analyzer rejected protected notifier
access in tests. The test helper was corrected using a subclass; no analyzer gate
was disabled. Two new brace-style information diagnostics were then corrected;
the final full-project analyzer count returned to the original 247.

## Minimal regression surface

- `flutter/lib/models/model.dart`: new session-owned observer and thin hooks at
  diagnostic snapshot ingestion and session start. Existing parser/fallback path
  is retained; a malformed diagnostic clears only the new observer.
- `flutter/lib/common/widgets/overlay.dart`: one entry in the existing quality
  overlay, using the existing dialog manager and current session permission state.
- `src/lang/*.rs`: 39 appended keys in 53 locale maps; complete Turkish values,
  English fallback elsewhere. Removing the new keys reproduces every old locale
  file byte-for-byte. Existing translations and keys are not rewritten.

There are no new package dependencies, native control/protocol changes, generated
FFI edits, backend requests, probes or automatic setting changes. The new timer
and listener only exist while the panel is mounted. The classifier stores only
bounded primitives and enumerated values, not the incoming event.

## Remaining acceptance and product boundaries

The report is an observation, not a health certificate, input-acceptance test or
license decision. Receipt freshness does not guarantee each metric was measured
recently; backend snapshots can carry last-known values. There are no packet-loss
or measured end-to-end input-latency claims. Relay and static-screen low FPS are
not treated as failures by themselves.

Copy is explicit and only copies the previewed JSON, but the OS clipboard may be
shared by existing clipboard synchronization or another application. The UI
warns about this. No automated upload or external support request is added.

The native Windows/macOS keyboard-grab path, Android soft keyboard, focus,
reconnect and on-device layout still require physical acceptance. Widget tests
and full Flutter tests do not establish those properties. Full native/platform
CI and publisher-signed artifacts remain separate requirements.

Existing paid-session licensing, billing/refund/recovery, signed updater and
production deployment blockers are unchanged. No master merge, visibility change,
live-site deployment, shipping APK/EXE or physical/game test is part of this work.
No independent reviewer was available; the change was self-reviewed and minimized.
