# VynxDesk Play Bridge

VynxDesk Play Bridge is the single supported hardware input model for the
consumer VynxDesk Play product. One RP2040 device exposes four HID reports:

- 128-key rollover keyboard state;
- five-button relative mouse with 16-bit deltas, vertical wheel, and pan;
- absolute mouse for desktop navigation;
- vendor input/output transport for 32-byte CRC-protected commands.

The Windows application opens only the vendor usage collection. Firmware turns
validated commands into standard HID keyboard and mouse input reports. No
kernel driver or installer is required for the bridge itself.

## Production hardware

Use one RP2040 or RP2350 board with native USB device support, external flash
with a stable unique ID, USB ESD protection, a data-capable connector, and a
sealed enclosure. The first production board should expose the BOOTSEL button
without requiring the enclosure to be opened.

The product must use an assigned USB VID/PID pair. Development values must not
be shipped, and another vendor's IDs must not be reused. The VID/PID are the
only intentionally unresolved production parameters.

## Firmware build

Install the Raspberry Pi Pico SDK and CMake, then run:

```powershell
.\build-firmware.ps1 `
  -UsbVid 0x0000 `
  -UsbPid 0x0000 `
  -PicoSdkPath C:\pico-sdk
```

Replace both zero values with the assigned identifiers. Hold BOOTSEL while
connecting the board and copy `build\vynx_input_bridge.uf2` to the RPI-RP2
volume.

## Windows product build

Use the same VID/PID values for the application:

```powershell
.\res\build-vynx-play.ps1 `
  -RendezvousServer 'relay.example.com' `
  -RendezvousPublicKey '<server-public-key>' `
  -UsbVid 0x0000 `
  -UsbPid 0x0000
```

The `vynx-play` feature includes both the user-mode compatibility profiles and
the physical bridge transport. At runtime the bridge is preferred
automatically. Unmappable Unicode text and events that started while the bridge
was unavailable remain on the existing Windows input path, including their
matching release event. This prevents mixed-source stuck keys.

## Acceptance gate

Do not ship a board until all checks pass on a clean Windows 10 and Windows 11
machine:

1. Device Manager shows the VynxDesk manufacturer/product and a unique serial.
2. No third-party driver or administrator prompt is required.
3. Keyboard rollover, left/right modifiers, navigation keys, numpad, and lock
   keys pass an HID test page.
4. Relative mouse movement, five buttons, wheel, and horizontal pan pass.
5. Absolute pointer reaches all four corners on a multi-monitor desktop.
6. Disconnecting the network, closing VynxDesk, unplugging USB, and a host crash
   release every held key and mouse button within the watchdog bound.
7. Unplug/replug reconnects without restarting VynxDesk.
8. A 60-minute key/mouse soak has zero malformed frames and zero stuck inputs.
9. End-to-end input latency is measured on production hardware and recorded;
   no latency number may be advertised from source inspection alone.
10. The firmware UF2, Windows binary, source archive, hashes, SBOM, and signing
    evidence identify the same release.

The firmware was compile-verified on this workstation with Arm GNU Toolchain
15.2.1, Pico SDK 2.3.1, TinyUSB, `-Wall -Wextra -Werror`, and test-only
VID/PID `0x0000:0x0000`. The resulting UF2 proves the source/toolchain build,
but it is not a shippable identity and has not been flashed or accepted on
physical hardware. A production claim still requires assigned IDs and the
acceptance gate above.
