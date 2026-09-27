# Audio dependency security remediation — 2026-09-26

RUSTSEC-2026-0293 was published on 2026-09-21. `ringbuf` before 0.5.2 can leave
already-dropped elements readable when an element destructor panics during
clear/skip. Upgrade the target-specific dependency from 0.3.3 to exactly 0.5.2.

The VynxDesk audio buffer stores `f32`, not elements with a custom destructor.
This change does not demonstrate remote exploitation in VynxDesk; it removes the
known vulnerable dependency and verifies preserved audio buffer semantics.

## Exact changes

- `Cargo.toml`: pin ringbuf 0.5.2 in the existing non-Linux target dependency.
- `src/client.rs`: import the new Consumer/Observer/RingBuffer traits and adapt
  three capacity queries to NonZeroUsize. No other audio path is rewritten.
- `Cargo.lock`: Cargo-resolved ringbuf checksum and new portable-atomic-util
  dependency. Cargo also rebound four existing dependency edges from the already
  present windows-sys 0.60.2 to the already present 0.61.2; both versions remain.
  Full native Windows/macOS/Android builds must verify that resolved graph.
- The new hardware-free probe compiles the exact AudioBuffer implementation from
  `src/client.rs`; it does not substitute a reimplementation or simulate a call.
- The final workflow is read-only. The one-time mutation workflow is removed.

## Evidence

Run: https://github.com/feyyaz54abidin-beep/VynxDesk/actions/runs/36204427284
Tested source commit: ddeb449fb18fb4e77bbd6817bfae1bcfafb6d5e5

The old dependency reached the assertions: four audio tests passed and the
panic-safety regression failed. After upgrading, all five passed. The probe
forgets the test ring buffer after catching the deliberate destructor panic so
it does not trigger the vulnerable second destruction on the old dependency.

The complete root `cargo audit --json` returned zero active vulnerabilities.
It still reported 19 unmaintained, two unsound and one yanked-package warnings.
These warnings are not suppressed and this result is not a claim of zero risk.

This is not a full client build, audio-device test, real remote session, APK
acceptance or proof that the combined Android/licensing branch has been tested
with this change. The PR remains draft until platform CI and acceptance pass.

Reference: https://rustsec.org/advisories/RUSTSEC-2026-0293.html
