# VynxDesk Windows desktop release profile

This profile covers the Windows desktop product only. Android packaging and licensing changes are intentionally outside its scope.

## Supported deployment

- Windows 10 version 2004 or later and Windows 11, x64.
- Windows Server 2022/2025 with Desktop Experience for interactive remote desktop use.
- Installed/service mode for unattended access, UAC handling and headless virtual display support.
- Portable mode for attended sessions only; it must not be advertised as full headless server support.

## Game and 3D profile

- Enable `Relative mouse mode` from the session toolbar for first-person, camera-controlled and 3D applications.
- Start with `Auto` codec and hardware codec enabled. Prefer H.264 when both endpoints expose a stable hardware implementation.
- Use 60 FPS only for the active game session. Keep the global/default rate at 30 FPS so idle and administrative sessions remain lightweight.
- Keep 4:4:4 color disabled unless text/color fidelity is more important than bandwidth and memory use.
- Disable remote cursor rendering while relative mouse mode is active; the current client already performs this automatically.
- Do not market universal game compatibility. Games that reject standard Windows synthetic input or protected surfaces require per-title acceptance testing.

## Headless and virtual-server profile

- Install VynxDesk as a service; do not use the portable package for unattended virtual machines.
- Ship `dylib_virtual_display.dll` beside `vynxdesk.exe`. The release packager fails when this component is absent.
- The existing display service creates a headless virtual display only when Windows reports no usable display and the installed platform supports IDD.
- Use Windows 10 build 19041 or later. Server Core is not a supported interactive desktop target.
- Validate reconnect after an RDP session is disconnected because session switching can temporarily hide physical displays.

## Low-resource profile

- Default to 30 FPS, balanced quality, automatic codec selection and a single active display.
- Prefer hardware encode/decode where supported; retain software fallback for incompatible GPUs and virtual machines.
- Avoid 4:4:4, simultaneous multi-display streaming and screen recording on low-memory hosts.
- Treat 60/120 FPS and very high custom bitrate as opt-in performance modes, not product defaults.

## Release gate

1. Build the Windows Flutter release and the virtual-display dynamic library.
2. Run `res/package-windows-desktop.ps1` against the Flutter release directory.
3. Provide the production `VYNXDESK_RENDEZVOUS_SERVER` and `VYNXDESK_RENDEZVOUS_PUB_KEY` values for a customer build.
4. Until a Windows publisher certificate is available, use `-AllowUnsigned` and distribute only the generated ZIP with its `SHA256SUMS.txt`. Mark the build as a manual-update release and keep automatic updates disabled.
5. Publish the matching AGPL source archive and notices with the binary distribution.
6. Run `install-vynxdesk.ps1` from the package as administrator on unattended Windows devices; it delegates the service installation to VynxDesk.
7. Complete a clean Windows 10, Windows 11 and Windows Server Desktop Experience acceptance pass before publishing.

## Acceptance matrix

| Area | Required scenario |
| --- | --- |
| Standard desktop | Direct and relayed connect, keyboard, absolute mouse, clipboard, audio and file transfer |
| Game input | Relative mouse capture, focus loss/re-entry, keyboard scan codes and disconnect cleanup |
| Graphics | DXGI desktop, windowed game, borderless game and supported hardware codec fallback |
| Headless VM | Cold boot without monitor, virtual display creation, reconnect and service restart |
| Session changes | RDP connect/disconnect, lock screen, UAC prompt and user switch |
| Resource use | 30 FPS idle/admin session and 60 FPS game session measured separately |
| Distribution | Hashes, source archive, notices, production server identity and, when available, trusted signatures |

The existing activation and license flow is deliberately unchanged by this desktop release profile.
