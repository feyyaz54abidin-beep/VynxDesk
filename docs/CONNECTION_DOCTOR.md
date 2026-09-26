# VYNX Connection Doctor

Additive, read-only connection diagnostics on top of Connection Insight. Open a
remote session, enable **Show quality monitor** in display options, then select
**Connection doctor** (Turkish: **Bağlantı tanılama**). The shared overlay exposes
the entry on mobile and desktop. It uses the existing session dialog/focus path;
no new remote control route is introduced.

## What it does

- Describes unavailable, connecting, disconnected, recent and stale observations.
- Reports unverified/unknown security, view-only mode and explicitly denied
  keyboard permission. Unknown permission is not treated as authorization.
- Shows known transport/codec/chroma and bounded numeric delay, bitrate and
  minimum FPS over recognized display indices. Relay routing is informational.
- A delay of at least 200 ms is an advisory, not a measured input-response time.
  Fewer than 15 FPS is informational: a static desktop can legitimately emit few
  frames. These thresholds are product heuristics, not universal performance SLAs.
- Observations older than 15 seconds (monotonic receipt age) lose their numeric
  display; they do not automatically mean the connection failed. A newly received
  snapshot may contain the backend's last-known metric values; this version does
  not have per-metric timestamps and does not measure packet loss or bandwidth.
- Reconnect/start clears feature-owned state. Invalid diagnostics clear the new
  observer without changing the legacy Connection Insight fallback behavior.

## Privacy and input boundary

The feature only observes the existing in-process diagnostic event. It sends no
network probe, keypress, HTTP request, telemetry or license request. It changes no
connection setting. Its report never serializes the raw event: only fixed enum
values, bounded integers/booleans and predetermined finding codes are permitted.
No peer IDs, IP addresses, user names, arbitrary codec/transport strings, paths,
credentials, screen images or typed text are copied into the report.

**Preview report** freezes the exact JSON shown. Copying is a separate explicit
operation; the frozen report is not silently replaced by later observations.
Copying uses the OS clipboard and can consequently be shared by existing clipboard
synchronization or other applications; the preview discloses this. Nothing is
uploaded automatically. There is no claim of a tamper-proof report.

The panel reuses the current overlay dialog and focus handling. Its timer and
listener exist only while mounted. Real Windows/macOS native keyboard-grab,
Android soft-keyboard and reconnect/focus behavior still require physical tests;
widget tests do not establish native input isolation.

## Implementation boundary

Runtime changes are confined to two existing Flutter files:
- models/model.dart: a feature-owned observer, two event/reset hooks, start reset.
- common/widgets/overlay.dart: the entry point using the existing session dialog.

New implementation is under lib/features/connection_doctor; localization entries
are appended with Turkish text and English fallback elsewhere. Native Rust code,
wire protocol, generated FFI, authentication, billing and relay decisions are
unchanged. Disabling the quality overlay hides the entry without replacing the
existing quality monitor implementation.

## Verification

`flutter test test/connection_doctor_test.dart test/connection_doctor_panel_test.dart`
`python -m unittest discover -s scripts/tests -p test_connection_doctor_contract.py`

The isolated feature probe and the complete project Flutter suite are distinct
checks. Exact executed results and evidence are recorded in the pull request.
The probe uses the actual feature source, not a reimplemented classifier.

Remaining product blockers (paid-session enforcement, production signing/deploy,
payment/refund recovery and physical acceptance) are not solved by diagnostics.
Control Deck and Device Wall are separate future features, not included here.
