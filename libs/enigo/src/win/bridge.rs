use hidapi::{HidApi, HidDevice};
use std::{
    convert::TryFrom,
    sync::{Arc, Mutex, OnceLock},
    time::{Duration, Instant},
};
use winapi::um::winuser::*;

const PROTOCOL_VERSION: u8 = 1;
const VENDOR_USAGE_PAGE: u16 = 0xFF00;
const VENDOR_USAGE: u16 = 0x0001;
const OUTPUT_REPORT_ID: u8 = 4;
const FRAME_BODY_SIZE: usize = 32;
const FRAME_SIZE: usize = FRAME_BODY_SIZE + 1;
const PAYLOAD_SIZE: usize = 20;
const PROBE_INTERVAL: Duration = Duration::from_secs(1);
const HEARTBEAT_INTERVAL: Duration = Duration::from_millis(200);

const COMMAND_KEYBOARD_STATE: u8 = 1;
const COMMAND_RELATIVE_MOUSE: u8 = 2;
const COMMAND_ABSOLUTE_MOUSE: u8 = 3;
const COMMAND_RELEASE_ALL: u8 = 4;
const COMMAND_HEARTBEAT: u8 = 5;

#[derive(Clone, Copy, Default)]
struct KeyboardState {
    modifiers: u8,
    usages: [u8; 16],
}

struct BridgeState {
    device: Option<HidDevice>,
    ids: Option<(u16, u16)>,
    sequence: u16,
    last_probe: Instant,
    last_write: Instant,
    keyboard: KeyboardState,
    software_keyboard: KeyboardState,
    mouse_buttons: u8,
    software_mouse_buttons: u8,
    active_sessions: usize,
    missing_ids_logged: bool,
}

impl BridgeState {
    fn new() -> Self {
        let now = Instant::now();
        Self {
            device: None,
            ids: configured_ids(),
            sequence: 0,
            last_probe: now - PROBE_INTERVAL,
            last_write: now,
            keyboard: KeyboardState::default(),
            software_keyboard: KeyboardState::default(),
            mouse_buttons: 0,
            software_mouse_buttons: 0,
            active_sessions: 0,
            missing_ids_logged: false,
        }
    }

    fn ensure_connected(&mut self) -> bool {
        if self.device.is_some() {
            return true;
        }
        let Some((vid, pid)) = self.ids else {
            if !self.missing_ids_logged {
                log::warn!(
                    "VynxDesk Play Bridge disabled: build-time USB VID/PID are not configured"
                );
                self.missing_ids_logged = true;
            }
            return false;
        };
        if self.last_probe.elapsed() < PROBE_INTERVAL {
            return false;
        }
        self.last_probe = Instant::now();

        let api = match HidApi::new() {
            Ok(api) => api,
            Err(error) => {
                log::debug!("Unable to initialize HID discovery: {}", error);
                return false;
            }
        };
        let Some(info) = api.device_list().find(|info| {
            info.vendor_id() == vid
                && info.product_id() == pid
                && info.usage_page() == VENDOR_USAGE_PAGE
                && info.usage() == VENDOR_USAGE
        }) else {
            return false;
        };
        match info.open_device(&api) {
            Ok(device) if device_is_compatible(&device) => {
                self.device = Some(device);
                self.keyboard = KeyboardState::default();
                self.mouse_buttons = 0;
                log::info!("VynxDesk Play Bridge connected");
                true
            }
            Ok(_) => {
                log::warn!("Ignoring incompatible VynxDesk Play Bridge protocol");
                false
            }
            Err(error) => {
                log::debug!("Unable to open VynxDesk Play Bridge: {}", error);
                false
            }
        }
    }

    fn send(&mut self, command: u8, payload: &[u8]) -> bool {
        if payload.len() > PAYLOAD_SIZE || !self.ensure_connected() {
            return false;
        }
        self.sequence = self.sequence.wrapping_add(1);
        let frame = encode_frame(command, self.sequence, payload);
        let result = self.device.as_ref().map(|device| device.write(&frame));
        match result {
            Some(Ok(written)) if written == frame.len() => {
                self.last_write = Instant::now();
                true
            }
            Some(Ok(written)) => {
                log::warn!(
                    "VynxDesk Play Bridge short write: {} of {} bytes",
                    written,
                    frame.len()
                );
                self.disconnect();
                false
            }
            Some(Err(error)) => {
                log::warn!("VynxDesk Play Bridge disconnected: {}", error);
                self.disconnect();
                false
            }
            None => false,
        }
    }

    fn disconnect(&mut self) {
        self.device = None;
        self.last_probe = Instant::now();
    }

    fn send_keyboard_usage(&mut self, usage: u8, down: bool) -> bool {
        if !down && keyboard_contains(&self.software_keyboard, usage) {
            set_keyboard_usage(&mut self.software_keyboard, usage, false);
            return false;
        }
        let previous = self.keyboard;
        if !set_keyboard_usage(&mut self.keyboard, usage, down) {
            return false;
        }

        let mut payload = [0u8; 17];
        payload[0] = self.keyboard.modifiers;
        payload[1..].copy_from_slice(&self.keyboard.usages);
        if self.send(COMMAND_KEYBOARD_STATE, &payload) {
            true
        } else {
            self.keyboard = previous;
            if down {
                set_keyboard_usage(&mut self.software_keyboard, usage, true);
            }
            false
        }
    }

    fn send_mouse(&mut self, flags: u32, data: u32, dx: i32, dy: i32) -> bool {
        if flags & MOUSEEVENTF_ABSOLUTE != 0 {
            return false;
        }
        let changed_button = mouse_button_mask(flags, data);
        if flags
            & (MOUSEEVENTF_LEFTUP | MOUSEEVENTF_RIGHTUP | MOUSEEVENTF_MIDDLEUP | MOUSEEVENTF_XUP)
            != 0
            && self.software_mouse_buttons & changed_button != 0
        {
            self.software_mouse_buttons &= !changed_button;
            return false;
        }
        let previous_buttons = self.mouse_buttons;
        self.update_mouse_buttons(flags, data);
        let supported = MOUSEEVENTF_MOVE
            | MOUSEEVENTF_LEFTDOWN
            | MOUSEEVENTF_LEFTUP
            | MOUSEEVENTF_RIGHTDOWN
            | MOUSEEVENTF_RIGHTUP
            | MOUSEEVENTF_MIDDLEDOWN
            | MOUSEEVENTF_MIDDLEUP
            | MOUSEEVENTF_XDOWN
            | MOUSEEVENTF_XUP
            | MOUSEEVENTF_WHEEL
            | MOUSEEVENTF_HWHEEL;
        if flags & supported == 0 {
            self.mouse_buttons = previous_buttons;
            return false;
        }

        let dx = dx.clamp(i16::MIN as i32, i16::MAX as i32) as i16;
        let dy = dy.clamp(i16::MIN as i32, i16::MAX as i32) as i16;
        let wheel = if flags & MOUSEEVENTF_WHEEL != 0 {
            wheel_delta(data)
        } else {
            0
        };
        let pan = if flags & MOUSEEVENTF_HWHEEL != 0 {
            wheel_delta(data)
        } else {
            0
        };
        let mut payload = [0u8; 7];
        payload[0] = self.mouse_buttons;
        payload[1..3].copy_from_slice(&dx.to_le_bytes());
        payload[3..5].copy_from_slice(&dy.to_le_bytes());
        payload[5] = wheel as u8;
        payload[6] = pan as u8;
        if self.send(COMMAND_RELATIVE_MOUSE, &payload) {
            true
        } else {
            self.mouse_buttons = previous_buttons;
            if flags
                & (MOUSEEVENTF_LEFTDOWN
                    | MOUSEEVENTF_RIGHTDOWN
                    | MOUSEEVENTF_MIDDLEDOWN
                    | MOUSEEVENTF_XDOWN)
                != 0
            {
                self.software_mouse_buttons |= changed_button;
            }
            false
        }
    }

    fn update_mouse_buttons(&mut self, flags: u32, data: u32) {
        for (down, up, mask) in [
            (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, 1 << 0),
            (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, 1 << 1),
            (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP, 1 << 2),
        ] {
            if flags & down != 0 {
                self.mouse_buttons |= mask;
            }
            if flags & up != 0 {
                self.mouse_buttons &= !mask;
            }
        }
        if flags & MOUSEEVENTF_XDOWN != 0 {
            self.mouse_buttons |= xbutton_mask(data);
        }
        if flags & MOUSEEVENTF_XUP != 0 {
            self.mouse_buttons &= !xbutton_mask(data);
        }
    }

    fn send_absolute_mouse(&mut self, x: u16, y: u16) -> bool {
        let mut payload = [0u8; 7];
        payload[0] = self.mouse_buttons;
        payload[1..3].copy_from_slice(&x.to_le_bytes());
        payload[3..5].copy_from_slice(&y.to_le_bytes());
        self.send(COMMAND_ABSOLUTE_MOUSE, &payload)
    }

    fn release_all(&mut self) -> bool {
        if self.send(COMMAND_RELEASE_ALL, &[]) {
            self.keyboard = KeyboardState::default();
            self.mouse_buttons = 0;
            true
        } else {
            false
        }
    }
}

fn device_is_compatible(device: &HidDevice) -> bool {
    let mut status = [0u8; FRAME_SIZE];
    status[0] = OUTPUT_REPORT_ID;
    match device.get_feature_report(&mut status) {
        Ok(size) if size >= 4 => {
            status[1] == b'V' && status[2] == b'X' && status[3] == PROTOCOL_VERSION
        }
        _ => false,
    }
}

fn bridge() -> Arc<Mutex<BridgeState>> {
    static BRIDGE: OnceLock<Arc<Mutex<BridgeState>>> = OnceLock::new();
    BRIDGE
        .get_or_init(|| {
            let state = Arc::new(Mutex::new(BridgeState::new()));
            let heartbeat_state = state.clone();
            if let Err(error) = std::thread::Builder::new()
                .name("vynx-input-bridge".to_owned())
                .spawn(move || loop {
                    std::thread::sleep(HEARTBEAT_INTERVAL);
                    let mut state = heartbeat_state
                        .lock()
                        .unwrap_or_else(|poisoned| poisoned.into_inner());
                    if state.device.is_some()
                        && state.active_sessions > 0
                        && state.last_write.elapsed() >= HEARTBEAT_INTERVAL
                    {
                        let _ = state.send(COMMAND_HEARTBEAT, &[]);
                    }
                })
            {
                log::warn!("Unable to start VynxDesk Play Bridge heartbeat: {}", error);
            }
            state
        })
        .clone()
}

pub(super) fn key_event(vk: u16, scan: u16, flags: u32) -> bool {
    if flags & KEYEVENTF_UNICODE != 0 {
        return false;
    }
    let scan = if flags & KEYEVENTF_EXTENDEDKEY != 0 && scan < 0x100 {
        0xE000 | scan as u32
    } else {
        scan as u32
    };
    let usage = if scan != 0 {
        scan_code_to_usage(scan)
    } else {
        virtual_key_to_usage(vk)
    };
    let Some(usage) = usage else {
        return false;
    };
    bridge()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .send_keyboard_usage(usage, flags & KEYEVENTF_KEYUP == 0)
}

pub(super) fn mouse_event(flags: u32, data: u32, dx: i32, dy: i32) -> bool {
    bridge()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .send_mouse(flags, data, dx, dy)
}

pub(super) fn absolute_mouse(x: i32, y: i32) -> bool {
    bridge()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .send_absolute_mouse(
            (x.clamp(0, u16::MAX as i32) / 2) as u16,
            (y.clamp(0, u16::MAX as i32) / 2) as u16,
        )
}

/// Sends a raw Windows keyboard event through an attached VynxDesk Play Bridge.
pub fn bridge_rdev_event(event: &rdev::EventType) -> bool {
    let (raw_key, down) = match event {
        rdev::EventType::KeyPress(rdev::Key::RawKey(raw_key)) => (raw_key, true),
        rdev::EventType::KeyRelease(rdev::Key::RawKey(raw_key)) => (raw_key, false),
        _ => return false,
    };
    let usage = match raw_key {
        rdev::RawKey::ScanCode(scan) => scan_code_to_usage(*scan),
        rdev::RawKey::WinVirtualKeycode(vk) => {
            u16::try_from(*vk).ok().and_then(virtual_key_to_usage)
        }
        _ => None,
    };
    let Some(usage) = usage else {
        return false;
    };
    bridge()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .send_keyboard_usage(usage, down)
}

/// Releases every keyboard key and mouse button held by the bridge.
pub fn release_all() -> bool {
    bridge()
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .release_all()
}

/// Marks a remote input session as active for bridge heartbeat management.
pub fn session_started() {
    let bridge = bridge();
    let mut state = bridge
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    state.active_sessions = state.active_sessions.saturating_add(1);
}

/// Marks a remote input session as closed and releases input after the last session.
pub fn session_ended() {
    let bridge = bridge();
    let mut state = bridge
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    state.active_sessions = state.active_sessions.saturating_sub(1);
    if state.active_sessions == 0 {
        let _ = state.release_all();
    }
}

fn configured_ids() -> Option<(u16, u16)> {
    Some((
        parse_usb_id(option_env!("VYNX_INPUT_BRIDGE_VID")?)?,
        parse_usb_id(option_env!("VYNX_INPUT_BRIDGE_PID")?)?,
    ))
}

fn parse_usb_id(value: &str) -> Option<u16> {
    let value = value.trim();
    if let Some(hex) = value
        .strip_prefix("0x")
        .or_else(|| value.strip_prefix("0X"))
    {
        u16::from_str_radix(hex, 16).ok()
    } else {
        value.parse().ok()
    }
}

fn encode_frame(command: u8, sequence: u16, payload: &[u8]) -> [u8; FRAME_SIZE] {
    let mut frame = [0u8; FRAME_SIZE];
    frame[0] = OUTPUT_REPORT_ID;
    let body = &mut frame[1..];
    body[0] = b'V';
    body[1] = b'X';
    body[2] = PROTOCOL_VERSION;
    body[3] = command;
    body[4..6].copy_from_slice(&sequence.to_le_bytes());
    body[6] = payload.len() as u8;
    body[8..8 + payload.len()].copy_from_slice(payload);
    let crc = crc16_ccitt(&body[..28]);
    body[28..30].copy_from_slice(&crc.to_le_bytes());
    frame
}

fn crc16_ccitt(data: &[u8]) -> u16 {
    let mut crc = 0xFFFFu16;
    for byte in data {
        crc ^= (*byte as u16) << 8;
        for _ in 0..8 {
            crc = if crc & 0x8000 != 0 {
                (crc << 1) ^ 0x1021
            } else {
                crc << 1
            };
        }
    }
    crc
}

fn xbutton_mask(data: u32) -> u8 {
    if data == XBUTTON1 as u32 {
        1 << 3
    } else {
        1 << 4
    }
}

fn mouse_button_mask(flags: u32, data: u32) -> u8 {
    if flags & (MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_LEFTUP) != 0 {
        1 << 0
    } else if flags & (MOUSEEVENTF_RIGHTDOWN | MOUSEEVENTF_RIGHTUP) != 0 {
        1 << 1
    } else if flags & (MOUSEEVENTF_MIDDLEDOWN | MOUSEEVENTF_MIDDLEUP) != 0 {
        1 << 2
    } else if flags & (MOUSEEVENTF_XDOWN | MOUSEEVENTF_XUP) != 0 {
        xbutton_mask(data)
    } else {
        0
    }
}

fn keyboard_contains(state: &KeyboardState, usage: u8) -> bool {
    if (0xE0..=0xE7).contains(&usage) {
        state.modifiers & (1u8 << (usage - 0xE0)) != 0
    } else if usage < 0x80 {
        state.usages[usage as usize / 8] & (1u8 << (usage % 8)) != 0
    } else {
        false
    }
}

fn set_keyboard_usage(state: &mut KeyboardState, usage: u8, down: bool) -> bool {
    if (0xE0..=0xE7).contains(&usage) {
        let mask = 1u8 << (usage - 0xE0);
        if down {
            state.modifiers |= mask;
        } else {
            state.modifiers &= !mask;
        }
        true
    } else if usage < 0x80 {
        let byte = usage as usize / 8;
        let mask = 1u8 << (usage % 8);
        if down {
            state.usages[byte] |= mask;
        } else {
            state.usages[byte] &= !mask;
        }
        true
    } else {
        false
    }
}

fn wheel_delta(data: u32) -> i8 {
    let value = data as i32;
    let wheel_delta = WHEEL_DELTA as i32;
    let detents = if value.abs() >= wheel_delta {
        value / wheel_delta
    } else {
        value.signum()
    };
    detents.clamp(i8::MIN as i32, i8::MAX as i32) as i8
}

fn virtual_key_to_usage(vk: u16) -> Option<u8> {
    let vk = vk as i32;
    match vk {
        0x41..=0x5A => Some(0x04 + (vk - 0x41) as u8),
        0x31..=0x39 => Some(0x1E + (vk - 0x31) as u8),
        0x30 => Some(0x27),
        VK_RETURN => Some(0x28),
        VK_ESCAPE => Some(0x29),
        VK_BACK => Some(0x2A),
        VK_TAB => Some(0x2B),
        VK_SPACE => Some(0x2C),
        VK_CAPITAL => Some(0x39),
        VK_F1..=VK_F12 => Some(0x3A + (vk - VK_F1) as u8),
        VK_INSERT => Some(0x49),
        VK_HOME => Some(0x4A),
        VK_PRIOR => Some(0x4B),
        VK_DELETE => Some(0x4C),
        VK_END => Some(0x4D),
        VK_NEXT => Some(0x4E),
        VK_RIGHT => Some(0x4F),
        VK_LEFT => Some(0x50),
        VK_DOWN => Some(0x51),
        VK_UP => Some(0x52),
        VK_LCONTROL => Some(0xE0),
        VK_LSHIFT | VK_SHIFT => Some(0xE1),
        VK_LMENU | VK_MENU => Some(0xE2),
        VK_LWIN => Some(0xE3),
        VK_RCONTROL | VK_CONTROL => Some(0xE4),
        VK_RSHIFT => Some(0xE5),
        VK_RMENU => Some(0xE6),
        VK_RWIN => Some(0xE7),
        _ => None,
    }
}

fn scan_code_to_usage(scan: u32) -> Option<u8> {
    let extended = scan >> 8 == 0xE0 || scan >> 8 == 0xE1;
    let code = (scan & 0xFF) as u8;
    if extended {
        return match code {
            0x1C => Some(0x58),
            0x1D => Some(0xE4),
            0x35 => Some(0x54),
            0x37 => Some(0x46),
            0x38 => Some(0xE6),
            0x47 => Some(0x4A),
            0x48 => Some(0x52),
            0x49 => Some(0x4B),
            0x4B => Some(0x50),
            0x4D => Some(0x4F),
            0x4F => Some(0x4D),
            0x50 => Some(0x51),
            0x51 => Some(0x4E),
            0x52 => Some(0x49),
            0x53 => Some(0x4C),
            0x5B => Some(0xE3),
            0x5C => Some(0xE7),
            0x5D => Some(0x65),
            _ => None,
        };
    }
    match code {
        0x01 => Some(0x29),
        0x02..=0x0A => Some(0x1E + code - 0x02),
        0x0B => Some(0x27),
        0x0C => Some(0x2D),
        0x0D => Some(0x2E),
        0x0E => Some(0x2A),
        0x0F => Some(0x2B),
        0x1C => Some(0x28),
        0x1D => Some(0xE0),
        0x2A => Some(0xE1),
        0x36 => Some(0xE5),
        0x38 => Some(0xE2),
        0x39 => Some(0x2C),
        0x3A => Some(0x39),
        0x3B..=0x44 => Some(0x3A + code - 0x3B),
        0x57 => Some(0x45),
        0x58 => Some(0x46),
        _ => scan_code_letter_or_numpad(code),
    }
}

fn scan_code_letter_or_numpad(code: u8) -> Option<u8> {
    const MAP: &[(u8, u8)] = &[
        (0x10, 0x14),
        (0x11, 0x1A),
        (0x12, 0x08),
        (0x13, 0x15),
        (0x14, 0x17),
        (0x15, 0x1C),
        (0x16, 0x18),
        (0x17, 0x0C),
        (0x18, 0x12),
        (0x19, 0x13),
        (0x1A, 0x2F),
        (0x1B, 0x30),
        (0x1E, 0x04),
        (0x1F, 0x16),
        (0x20, 0x07),
        (0x21, 0x09),
        (0x22, 0x0A),
        (0x23, 0x0B),
        (0x24, 0x0D),
        (0x25, 0x0E),
        (0x26, 0x0F),
        (0x27, 0x33),
        (0x28, 0x34),
        (0x29, 0x35),
        (0x2B, 0x31),
        (0x2C, 0x1D),
        (0x2D, 0x1B),
        (0x2E, 0x06),
        (0x2F, 0x19),
        (0x30, 0x05),
        (0x31, 0x11),
        (0x32, 0x10),
        (0x33, 0x36),
        (0x34, 0x37),
        (0x35, 0x38),
        (0x37, 0x55),
        (0x45, 0x53),
        (0x46, 0x47),
        (0x47, 0x5F),
        (0x48, 0x60),
        (0x49, 0x61),
        (0x4A, 0x56),
        (0x4B, 0x5C),
        (0x4C, 0x5D),
        (0x4D, 0x5E),
        (0x4E, 0x57),
        (0x4F, 0x59),
        (0x50, 0x5A),
        (0x51, 0x5B),
        (0x52, 0x62),
        (0x53, 0x63),
    ];
    MAP.iter()
        .find_map(|(scan, usage)| (*scan == code).then_some(*usage))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crc_matches_ccitt_false_reference() {
        assert_eq!(crc16_ccitt(b"123456789"), 0x29B1);
    }

    #[test]
    fn frame_contains_report_id_payload_and_crc() {
        let frame = encode_frame(COMMAND_HEARTBEAT, 0x1234, &[7, 8]);
        assert_eq!(frame[0], OUTPUT_REPORT_ID);
        assert_eq!(&frame[1..3], b"VX");
        assert_eq!(frame[4], COMMAND_HEARTBEAT);
        assert_eq!(&frame[5..7], &0x1234u16.to_le_bytes());
        assert_eq!(frame[7], 2);
        assert_eq!(&frame[9..11], &[7, 8]);
        assert_eq!(
            u16::from_le_bytes([frame[29], frame[30]]),
            crc16_ccitt(&frame[1..29])
        );
    }

    #[test]
    fn maps_standard_and_extended_scan_codes() {
        assert_eq!(scan_code_to_usage(0x001E), Some(0x04));
        assert_eq!(scan_code_to_usage(0xE01D), Some(0xE4));
        assert_eq!(scan_code_to_usage(0xE04D), Some(0x4F));
    }

    #[test]
    fn parses_decimal_and_hex_usb_ids() {
        assert_eq!(parse_usb_id("4660"), Some(0x1234));
        assert_eq!(parse_usb_id("0x1234"), Some(0x1234));
        assert_eq!(parse_usb_id("nope"), None);
    }

    #[test]
    fn keyboard_state_tracks_key_and_modifier() {
        let mut state = KeyboardState::default();
        assert!(set_keyboard_usage(&mut state, 0x04, true));
        assert!(set_keyboard_usage(&mut state, 0xE1, true));
        assert!(keyboard_contains(&state, 0x04));
        assert!(keyboard_contains(&state, 0xE1));
        assert!(set_keyboard_usage(&mut state, 0x04, false));
        assert!(!keyboard_contains(&state, 0x04));
        assert!(keyboard_contains(&state, 0xE1));
    }

    #[test]
    fn mouse_button_mapping_includes_navigation_buttons() {
        assert_eq!(mouse_button_mask(MOUSEEVENTF_LEFTDOWN, 0), 1);
        assert_eq!(mouse_button_mask(MOUSEEVENTF_XDOWN, XBUTTON1 as u32), 1 << 3);
        assert_eq!(mouse_button_mask(MOUSEEVENTF_XUP, XBUTTON2 as u32), 1 << 4);
    }
}
