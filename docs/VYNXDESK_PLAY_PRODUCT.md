# VynxDesk Play product definition

## Single commercial model

The consumer product is sold as **VynxDesk Play Bridge**. The package contains:

- one provisioned VynxDesk Play Bridge USB device;
- the Windows host/controller application;
- access to the VynxDesk rendezvous and relay service;
- firmware and desktop updates for the purchased support period;
- the complete corresponding source required by the product license.

There is no separate software-only SKU. If the bridge is temporarily absent,
the same application falls back to its standard Windows input compatibility
path so the customer can still recover the PC and reconnect the hardware.

## Customer setup

1. Install VynxDesk Play on the gaming PC.
2. Plug the supplied bridge into a native USB port on that PC.
3. Wait for the bridge LED to become steady.
4. Pair the controller device with the PC.
5. Enable relative mouse mode for first-person or camera-controlled games.

The bridge LED blinks slowly before USB enumeration, blinks quickly during a
release/reset sequence, stays on while the application heartbeat is active,
and blinks at a medium rate while mounted but waiting for VynxDesk.

## Supported input surface

- NKRO keyboard usages 0 through 127 and eight left/right modifiers;
- relative mouse with five buttons, 16-bit X/Y deltas, wheel, and pan;
- absolute pointer for desktop navigation;
- automatic reconnect and one-second device reprobe;
- 750 ms firmware watchdog and last-session release;
- protocol-version handshake and CRC-16/CCITT frame validation;
- source-stable software fallback for unmappable Unicode and absent hardware.

## Claims gate

The following may be claimed after the clean-machine and hardware acceptance
tests pass: driverless USB input bridge, automatic detection, five-button mouse,
NKRO keyboard, absolute/relative pointer modes, and automatic stuck-input
release.

Do not advertise “undetectable,” “anti-cheat bypass,” “zero latency,” “works in
every game,” or a measured polling/latency figure without current production
hardware evidence. The bridge identifies itself as VynxDesk hardware and does
not impersonate another vendor's device.

## Release blockers

- assigned, non-zero USB VID/PID;
- production PCB/enclosure and USB electrical/ESD validation;
- a physical-board Windows 10/11 acceptance run;
- publisher code-signing certificate for the Windows package;
- production rendezvous/relay endpoint and matching public key;
- clean install/update/uninstall and 60-minute input soak evidence;
- final pricing, warranty, returns, privacy, and support terms.

Source compilation is complete only at the offline/toolchain level until these
external inputs and physical acceptance evidence exist.
