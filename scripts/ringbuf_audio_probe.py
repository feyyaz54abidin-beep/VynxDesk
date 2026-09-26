#!/usr/bin/env python3
"""Compile actual AudioBuffer source without devices; does not test live audio."""
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'src/client.rs').read_text(encoding='utf-8')
version = tomllib.loads((ROOT / 'Cargo.toml').read_text())['dependencies']['ringbuf']
start = source.index('struct AudioBuffer(')
end = source.index('\nimpl AudioHandler {', start)
audio = source[start:end].replace('#[cfg(not(target_os = "linux"))]\n', '')
imports = re.search(r'^use ringbuf::[^;]+;', source, re.M).group()
constant = re.search(r'^pub const AUDIO_BUFFER_MS: usize = \d+;', source, re.M).group()
tests = r'''
#[test]
fn clear_advances_past_an_element_whose_drop_panics() {
    struct Panics;
    impl Drop for Panics { fn drop(&mut self) { panic!("expected destructor panic"); } }
    let mut rb = ringbuf::HeapRb::<Panics>::new(1);
    rb.push_overwrite(Panics);
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| { rb.clear(); }));
    let remaining = rb.occupied_len();
    // Do not invoke the old vulnerable destructor after a failed assertion.
    std::mem::forget(rb);
    assert!(result.is_err());
    assert_eq!(remaining, 0, "a dropped element must not remain readable");
}
fn buffer(capacity: usize) -> AudioBuffer {
    AudioBuffer(Arc::new(std::sync::Mutex::new(ringbuf::HeapRb::new(capacity))), 1000, [0;30])
}
#[test]
fn append_retains_order_and_drains() {
    let b = buffer(4);
    assert_eq!(b.append_pcm2(&[1.,2.,3.]), 3);
    let mut output = [0.;4];
    let mut lock = b.0.lock().unwrap();
    assert_eq!(lock.pop_slice(&mut output), 3);
    assert_eq!(output, [1.,2.,3.,0.]);
    assert_eq!(lock.occupied_len(), 0);
}
#[test]
fn oversized_frame_retains_most_recent_samples() {
    let b = buffer(4);
    assert_eq!(b.append_pcm2(&[1.,2.,3.,4.,5.,6.]), 4);
    let mut output = [0.;4];
    b.0.lock().unwrap().pop_slice(&mut output);
    assert_eq!(output, [3.,4.,5.,6.]);
}
#[test]
fn partial_overflow_drops_oldest_samples() {
    let b = buffer(4);
    b.append_pcm2(&[1.,2.,3.]);
    assert_eq!(b.append_pcm2(&[4.,5.]), 4);
    let mut output = [0.;4];
    b.0.lock().unwrap().pop_slice(&mut output);
    assert_eq!(output, [2.,3.,4.,5.]);
}
#[test]
fn resize_clears_samples_only_when_capacity_changes() {
    let mut b = AudioBuffer::default();
    b.append_pcm2(&[1.,2.]);
    b.resize(48000, 2);
    assert_eq!(b.0.lock().unwrap().occupied_len(), 2);
    b.resize(24000, 1);
    assert_eq!(b.0.lock().unwrap().occupied_len(), 0);
    assert_eq!(b.1, 24000);
}
'''
with tempfile.TemporaryDirectory(prefix='vynxdesk-audio-probe-') as d:
    root = Path(d)
    (root / 'src').mkdir()
    (root / 'Cargo.toml').write_text('[package]\nname="vynxdesk-audio-probe"\nversion="0.0.0"\nedition="2021"\n[dependencies]\nringbuf="' + version + '"\nchrono="=0.4.41"\nlog="=0.4.27"\n')
    (root / 'src/lib.rs').write_text('#![allow(dead_code)]\nuse std::sync::Arc;\n' + imports + '\n' + constant + '\n' + audio + tests)
    result = subprocess.run(['cargo','test','--manifest-path',str(root / 'Cargo.toml'),'--','--test-threads=1'])
    raise SystemExit(result.returncode)
