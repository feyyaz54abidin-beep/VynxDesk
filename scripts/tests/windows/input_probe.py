#!/usr/bin/env python3
"""Run isolated *actual source functions* against Windows; not a full client/game test."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
source = (ROOT / "libs/enigo/src/win/win_impl.rs").read_text(encoding="utf-8")

def function(name):
    match = re.search(r"^fn " + name + r"\([^\n]*\)[^{]*\{.*?^\}", source, re.M | re.S)
    if not match:
        raise RuntimeError(f"Cannot find real production function {name}")
    return match.group(0)

# The declarations below call the OS, not mocks. Function bodies are never copied by hand.
preamble = r'''
#![allow(non_camel_case_types, dead_code, non_snake_case)]
type DWORD = u32;
type LPARAM = isize;
const KEYEVENTF_EXTENDEDKEY: u32 = 1;
const KEYEVENTF_KEYUP: u32 = 2;
const FORMAT_MESSAGE_IGNORE_INSERTS: u32 = 0x200;
const FORMAT_MESSAGE_FROM_SYSTEM: u32 = 0x1000;
const FORMAT_MESSAGE_ARGUMENT_ARRAY: u32 = 0x2000;
#[link(name = "kernel32")]
extern "system" {
    fn GetLastError() -> DWORD;
    fn SetLastError(error: DWORD);
    fn FormatMessageW(flags: u32, source: *const u8, message: u32, language: u32,
        buffer: *mut u16, size: u32, args: *mut u8) -> u32;
}
'''
tests = r'''
#[test] fn known_error_keeps_complete_os_message() {
    let expected = std::io::Error::from_raw_os_error(5).to_string();
    unsafe { SetLastError(5) };
    assert_eq!(get_error(), expected);
}
#[test] fn unknown_error_never_reports_success() {
    unsafe { SetLastError(0xE0000001) };
    assert!(!get_error().is_empty());
}
#[test] fn zero_last_error_explains_uipi() {
    unsafe { SetLastError(0) };
    assert!(get_error().contains("UIPI"));
}
#[test] fn key_up_has_extended_previous_and_transition_bits() {
    assert_eq!(legacy_keyboard_lparam(0xE01D, 3) as u32, 0xC11D0001);
}
#[test] fn ordinary_key_down_has_no_key_up_bits() {
    assert_eq!(legacy_keyboard_lparam(0x1E, 0) as u32, 0x001E0001);
}
'''
with tempfile.TemporaryDirectory(prefix="vynxdesk-native-input-") as directory:
    root = Path(directory)
    path = root / "input.rs"
    path.write_text(preamble + function("get_error") + "\n" + function("legacy_keyboard_lparam") + tests, encoding="utf-8")
    exe = root / "input-tests.exe"
    subprocess.run(["rustc", "--edition=2021", "--test", str(path), "-o", str(exe)], check=True)
    subprocess.run([str(exe), "--test-threads=1"], check=True)
