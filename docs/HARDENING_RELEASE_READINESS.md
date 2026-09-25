# VynxDesk release readiness — 2026-09-26

## This changeset

The supported product remains Flutter-first with the existing RustDesk wire
protocol. Changes are intentionally limited to evidenced input, distribution,
source-export and CI defects. No control-plane, billing service, anti-cheat
bypass, protocol rewrite or physical USB hardware has been implemented here.

- Windows input errors now preserve OS error text and never silently report
  success when Windows provides no useful last-error code. The existing window
  message fallback sets extended-key and key-release transition bits correctly.
- `build.py --flutter --windows-input-plus` explicitly includes the existing
  host compatibility profiles. The Windows Flutter CI matrix uses it. The
  standard profile and builds without this flag keep their normal behavior.
- Windows packages require the Rust runtime DLL, archive literal directories
  correctly, include read-only support diagnostics, and reject invalid signatures
  even in the explicitly unsigned manual distribution profile.
- The installer preflight works on Windows PowerShell 5.1 and PowerShell 7.
- Source packages contain committed Git objects and exact initialized submodule
  revisions. Dirty tracked source, missing/mismatched submodules, obvious tracked
  private-key files and PEM private-key blocks are rejected. Untracked files are
  never included. This is not a general-purpose secret scanner.
- Source ZIP/tar.gz files preserve source modes and include
  `VYNXDESK_SOURCE.json`. Repeat exports with the same source and packaging
  toolchain are deterministic. Python 3.10+ and Git are required.
- Production identity validation rejects malformed endpoints/keys and the
  upstream debug identity without echoing configuration values.
- Unsupported Windows 32-bit Sciter is opt-in through
  `build-legacy-windows-sciter`; its known Rust ABI/MSRV conflict remains a
  separate investigation. It is not advertised as fixed or supported. Supported
  Flutter publishing does not depend on an optional Sciter artifact existing.

## Verification scope

`python -m unittest discover -s scripts/tests -v` exercises real temporary Git
repositories and the production Python functions. `PyYAML` is needed for the CI
configuration contract tests.

On Windows, `powershell -NoProfile -File scripts/tests/windows/distribution.ps1`
and the same command under `pwsh` exercise real packaging ZIPs and the installer
preflight with synthetic binary fixtures. Signature statuses are deliberately
mocked; these tests do not prove trust of any customer binary.

`python scripts/tests/windows/input_probe.py` compiles the actual small Rust
production function bodies against Windows APIs and checks errors/key flags.
It is an isolated native regression probe, **not** a full Enigo/client build,
a live remote session or a game acceptance test. Rust unit regressions are also
included in the Enigo crate for platform CI. Existing full Flutter CI remains
required before merge.

## Release blockers — do not replace evidence with a checkbox

| Gate | Required evidence |
| --- | --- |
| Build | Successful full CI at the exact candidate commit; source archive maps to the binaries actually built |
| Production identity | Protected rendezvous host and matching 32-byte public key; live direct and relay tests from separate networks |
| Trust | Trusted publisher signing and timestamp verification on contained binaries and final installer |
| Windows acceptance | Clean install/uninstall, service/UAC, unattended access, headless display, file transfer and reconnect on the supported OS matrix |
| Game support | Per-title/version press/release, relative mouse, focus-loss and reconnect results; API success alone is insufficient |
| USB bridge | Assigned VID/PID, physical-board/electrical validation, watchdog and input soak evidence; no such evidence is created by this changeset |
| Distribution | Exact source, notices, dependency audit, SBOM, full package checksums and manual rollback procedure |
| Commercial terms | Distributor identity, support, warranty/returns, service privacy/retention and final offer |

Unsigned manual packages remain explicitly unsigned with automatic updates
disabled. A checksum is not publisher authentication. Do not claim “bug-free”,
“works in every game”, “undetectable” or “ready for sale” from source-only tests.

## Regression surface

Existing runtime behavior changed only in Windows input error reporting and the
existing failed-injection window-message fallback. Other changes are confined
to opt-in feature selection, packaging, release validation and CI. Generated
Flutter bridges, root protocol types, relay transport and hardware firmware
are unchanged. Internal `rustdesk`/`librustdesk` names and AGPL notices remain.
