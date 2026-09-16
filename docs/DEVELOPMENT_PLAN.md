# VynxDesk Development Plan

## Objective

Evolve VynxDesk as a Flutter-first remote desktop product without changing the
RustDesk wire protocol, destabilizing the legacy Sciter path, or combining
upstream synchronization with product changes. `ARCHITECTURE.md` defines the
module boundaries; this document defines the delivery order and acceptance
evidence.

## Delivery Rules

- Make one independently reversible product or platform change per pull request.
- Preserve the existing runtime path when a new capability is disabled or not
  supported by the current peer or platform.
- Add an observable contract before extracting or rewriting an established
  subsystem.
- Treat endpoint configuration, signing identity, submodule availability, and
  release certificates as release inputs, not source-code defaults.
- Keep relay/rendezvous transport focused on data-plane responsibilities.
  Inventory, account, policy, and audit-retention features belong in a separate
  control plane.

## Delivery Sequence

| Phase | Scope | Exit evidence | Rollback boundary |
| --- | --- | --- | --- |
| 0. Source ownership | Git baseline, upstream reference, nested dependency ownership | Baseline tag, clean object database, documented upstream procedure | Revert a normal root commit; do not rewrite the baseline tag |
| 1. Build and supply chain | Toolchain contract, reproducible dependency baseline, CI quality gates, RustSec scan | Contract checker, CI workflow parse, locked build/test, no active RustSec advisory | Revert the focused build or lockfile commit |
| 2. Connection Insight | Non-identifying session lifecycle and quality snapshot for Flutter | Rust state tests, Dart parsing tests, existing quality-monitor fallback retained | Stop emitting the additive event; legacy quality events continue unchanged |
| 3. Session reliability | Reconnect, transport-selection, codec-fallback, and permission-state contract tests | Deterministic fixture coverage for direct, relay, WebRTC, reconnect, and disconnect rounds | Keep the current transport decision flow and remove only the new observer or fixture |
| 4. Flutter feature modularization | Move new feature state into feature-owned models only after its event/API contract is stable | Widget/model tests, generated bridge remains untouched unless API changes require regeneration | Leave existing global models in place; do not perform a cosmetic migration |
| 5. Windows platform acceptance | Service mode, virtual display, relative input, RDP transitions, codecs, and device recovery | Clean Windows 10, Windows 11, and Windows Server Desktop Experience acceptance matrix | Disable the platform capability through its existing capability check; preserve standard desktop access |
| 6. Release and operations | Controlled `hbb_common` fork, production identity, signed package, SBOM, source archive, and rollout checks | Remote CI checkout, release build, package gate, hashes, signature verification, staged acceptance | Hold publication; never substitute debug/public rendezvous identity in a production binary |

## Current Baseline

Phases 0 through 3 have implementation evidence in the current root history.
Phase 6 has its preflight contract and supply-chain checks in place, but its
external production inputs are intentionally still outstanding:

- `vynxdesk-baseline-2026-09-15` identifies the imported VynxDesk source
  baseline.
- `upstream/master` is a fetched reference, not an implicitly merged source.
- `toolchain-versions.toml` and `scripts/check_build_contract.py` establish the
  build-version contract.
- CI checks RustSec advisories, changed Rust formatting/Clippy findings, and
  Flutter analysis/tests without turning unrelated legacy diagnostics into a
  merge blocker.
- The manual release preflight validates protected rendezvous inputs, remote
  submodule reachability, the locked release build, and dependency audit before
  packaging.
- `.gitmodules` points `libs/hbb_common` at the VynxDesk-controlled fork and
  the root gitlink is remotely fetchable by the release contract check.
- `ConnectionDiagnosticsSnapshot` emits lifecycle, security, path, and quality
  information without peer IDs, IP addresses, credentials, or payload content.
- Reconnect-round tests prove that an old disconnect cannot transition a newer
  connection round, including after the counter wraps.

## Immediate Next Work

1. Extend the Phase 3 fixture suite before changing rendezvous, punch, relay,
   WebRTC, or reconnect selection. Each fixture must assert the selected path
   and resulting lifecycle rather than infer success from logging.
2. Add VM-backed Windows acceptance jobs only after their artifacts and device
   setup are reproducible. A local desktop run is not evidence for service,
   virtual-display, RDP, or protected-input behavior.
3. Set the production rendezvous host and public key as protected release
   inputs, then perform the Phase 6 release build. Never commit either value as
   a fallback; the private rendezvous key must never enter this repository.
4. Provision the Windows, Apple, and Android signing identities, then verify
   package signatures and clean-machine installation against the signed release
   artifacts.

## Acceptance Matrix

| Area | Required proof before expansion |
| --- | --- |
| Protocol compatibility | Current peer can connect through direct, relay, and supported WebRTC paths without a generated-bridge or wire-format change |
| Session lifecycle | A new round cannot be marked disconnected by an older round; the UI observes connecting, connected, and disconnected transitions |
| Quality reporting | Partial speed/FPS and delay/bitrate updates merge into one snapshot while existing UI events remain unchanged |
| Flutter UI | Parser and widget-facing state work with absent or legacy event fields and preserve the current WebRTC/TURN fallback |
| Localization | New visible keys exist in `template.rs` and every locale map; empty translations use the existing English fallback |
| Dependencies | Locked build passes and `cargo audit` has no active vulnerability; maintenance warnings are tracked separately |
| Release | Production endpoint/public key, controlled submodules, package hashes, source archive, SBOM, and signing policy are present |

## Explicit Non-Goals

- Do not rewrite the custom remote desktop protocol during a Flutter or UI
  modernization.
- Do not migrate the legacy Sciter UI solely to make module names consistent.
- Do not turn pre-existing project-wide lint, analyzer, or formatting debt into
  a gate for unrelated changed lines.
- Do not add product control-plane state to `hbb_common`, the rendezvous server,
  or the relay without an independently designed service boundary.
