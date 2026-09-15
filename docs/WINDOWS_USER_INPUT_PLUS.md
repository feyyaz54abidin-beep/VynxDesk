# Windows User Input Plus

`windows-user-input-plus` is a Windows-only, build-time product capability for
selecting the user-mode keyboard injection path used by a custom VynxDesk
client. It does not install a driver and does not claim to create hardware or
Raw Input events.

Build the paid/custom-client binary with:

```powershell
cargo build --release --features windows-user-input-plus
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
