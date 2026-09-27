# Windows User Input Plus

`windows-user-input-plus` is a Windows-only, build-time product capability for
selecting the user-mode keyboard injection path used by a custom VynxDesk
client. It does not install a driver and does not claim to create hardware or
Raw Input events.

Build the paid/custom-client binary with:

```powershell
python build.py --flutter --hwcodec --windows-input-plus
```

Set `windows-input-compatibility-profile` in the signed custom-client advanced
settings. The setting is read once, when the host first initializes input.

For a customer build that must keep its assigned profile, place it under the
signed `override-settings` object:

```json
{
  "override-settings": {
    "windows-input-compatibility-profile": "virtual-key"
  }
}
```

| Value | Behavior | Intended target |
| --- | --- | --- |
| `standard` | Existing VynxDesk behavior | Default |
| `scan-code` | Existing scan-code-first `SendInput` behavior | Shortcuts, games that accept `SendInput` |
| `virtual-key` | Emits virtual-key `SendInput` events | Layout-aware desktop applications |
| `legacy-window` | Posts keyboard messages to the foreground window and mouse button/wheel messages to the window under the pointer | Legacy Win32 applications |

Unknown or empty values resolve to `standard`. Builds without the feature keep
the original implementation and ignore this product option.

Absolute and relative pointer movement retain the existing system-wide path.
The legacy profile maintains button state across down/up messages and emits
client coordinates for buttons and screen coordinates for wheel messages, as
required by Win32.

## What this does not establish

A successful `SendInput` call only establishes insertion into the Windows input
stream. It does not prove that an application consumed it. UIPI can block input
across integrity levels without a useful last-error value. Window messages are
not equivalent to Raw Input; a protected application may deliberately reject
synthetic input. Do not remove OS or game protections to claim compatibility.

The `standard` profile remains the default. `scan-code` is not a new bypass; it
uses the existing scan-code-first path. Use `virtual-key` only for applications
that expect virtual keys. Use `legacy-window` only for compatible Win32 message
consumers. Keyboard mode and the input backend are distinct: test the actual
Translate/Map/Legacy mode used by the session, since not every route uses Enigo.
The build flag does not enable the USB bridge or install a driver.

## Support procedure

Run `powershell -NoProfile -File .\diagnose-input.ps1` on the host. This is a
read-only local report; it does not press keys or send telemetry. Optional
`-OutputPath .\input-report.json` creates a new report without overwriting one.
It does not measure a game's integrity level or test game acceptance.

For each reported issue, reproduce first in a plain desktop editor and then the
affected application's focused, windowed session. Check host installation mode,
UAC/integrity context, selected keyboard mode and signed input profile. Test left
and right modifiers, extended keys, press/release pairs, mouse buttons/wheel,
relative motion and reconnect/focus loss. Record the exact client build, host OS,
application version, input mode, transport and result. Do not advertise a title
as supported until that title has passed on a clean machine.

Reference contracts: Microsoft Learn `SendInput`, `KEYBDINPUT`, `WM_KEYUP`.
