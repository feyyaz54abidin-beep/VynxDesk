# VynxDesk Architecture

## Product Direction

VynxDesk is a Flutter-first remote desktop product built on the RustDesk
protocol stack. Flutter is the active product shell. The Sciter path remains a
legacy compatibility surface and must not receive new product features unless a
Flutter-equivalent implementation is impossible.

```text
Flutter feature UI
        |
        v
Versioned session event and command boundary
        |
        v
Rust application layer
  |- session lifecycle and diagnostics
  |- transport selection and connection policy
  |- host services: input, clipboard, files, terminal, printer
  |- media: capture, codec, QoS, audio
        |
        v
hbb_common protocol and transport primitives
        |
        +-- direct TCP/UDP/KCP/WebRTC
        +-- hbbs rendezvous / hbbr relay
        +-- platform adapters and VynxDesk Play input bridge
```

`hbbs` and `hbbr` remain rendezvous and relay components. Device inventory,
policy delivery, account management, and audit retention belong to a separate
control-plane service when those product requirements are introduced. They must
not be added to the relay protocol or `hbb_common` configuration layer.

## Incremental Boundaries

The application remains a modular monolith while compatibility with the
RustDesk protocol is preserved. New features follow these boundaries:

- `src/session_diagnostics.rs` owns session lifecycle and non-identifying
  connection snapshots.
- `src/ui_session_interface.rs` exposes thin session hooks and keeps existing
  connection, relay, and capture behavior intact.
- `src/flutter.rs` adapts typed Rust snapshots to the existing Flutter event
  stream. Generated Flutter bridge files remain generated artifacts.
- Flutter additions belong to feature-specific presentation/application/data
  folders when a feature grows beyond an existing model. Existing global models
  are not migrated solely for consistency.
- Platform-specific behavior stays behind platform adapters. VynxDesk Play is
  an input backend with capability and health reporting, not a special case in
  the generic session transport code.

## Connection Insight

The initial vertical slice is Connection Insight. It combines the already
available connection path and QoS measurements into a `ConnectionDiagnosticsSnapshot`:

- lifecycle: `idle`, `connecting`, `connected`, `disconnected`;
- security and direct/relayed outcome;
- chosen transport, including WebRTC and relay paths;
- speed, per-display FPS, delay, target bitrate, codec, and chroma.

The snapshot deliberately excludes peer identifiers, IP addresses, credentials,
and packet payloads. Flutter receives it through the existing per-session event
stream and shows state, security, and path in the quality monitor. Existing
connection events remain unchanged for legacy consumers.

## Delivery Sequence

1. Keep the Git baseline and build contract current before merging upstream
   changes.
2. Add new behavior as a focused session or platform module with a thin hook in
   existing code.
3. Add unit tests for state transitions and Flutter parsing before UI expansion.
4. Add VM-backed end-to-end coverage for Windows service, virtual display,
   input, reconnect, relay fallback, and codec fallback as each platform path is
   changed.
5. Extract larger areas of `client.rs` and `server/connection.rs` only after a
   new module owns a stable contract and has regression coverage.

Do not combine a Flutter/FRB upgrade, an upstream merge, and an architecture
refactor in one change. Each has a separate compatibility and rollback surface.
