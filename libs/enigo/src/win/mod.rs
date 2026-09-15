mod win_impl;

#[cfg(feature = "vynx-input-bridge")]
mod bridge;

pub mod keycodes;
pub use self::win_impl::{Enigo, ENIGO_INPUT_EXTRA_VALUE};

#[cfg(feature = "vynx-input-bridge")]
pub use self::bridge::{
    bridge_rdev_event, release_all as bridge_release_all, session_ended as bridge_session_ended,
    session_started as bridge_session_started,
};
