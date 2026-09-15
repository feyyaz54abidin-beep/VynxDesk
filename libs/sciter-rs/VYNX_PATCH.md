# Sciter behavior-event compatibility

Vendored unchanged from rustdesk-org/rust-sciter revision
5322f3a755a0e6bf999fbc60d1efc35246c0f821 (dyn), except src/eventhandler.rs
and a Cargo.toml lint setting.
MIT license is retained in LICENSE.

Native menu events with cmd=0x1d caused a non-unwinding Rust panic at the
unchecked BEHAVIOR_EVENTS transmute, terminating the GUI while the tray remained.
The behavior callback now checks event, phase and edit-reason discriminants.
Unknown values return unhandled; known values keep their previous dispatch.
No Sciter DLL change or UI/menu redesign is included.

Vendoring removes Cargo's dependency lint cap. The manifest explicitly allows
the existing invalid_reference_casting diagnostic in value.rs to preserve the
previous build behavior; that pre-existing unsafe implementation is not fixed
or otherwise changed by this menu-event patch.
