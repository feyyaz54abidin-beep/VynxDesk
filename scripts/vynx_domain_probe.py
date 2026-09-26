#!/usr/bin/env python3
"""Compile the actual public-service classifier with its pinned URL parser."""
from pathlib import Path
import subprocess
import tempfile
import tomllib

root = Path(__file__).resolve().parents[1]
source = (root / 'src/common.rs').read_text(encoding='utf-8')
start = source.index('pub fn is_public(url: &str) -> bool {')
end = source.index('\npub fn get_tcp_punch_enabled()', start)
body = source[start:end]
version = next(p['version'] for p in tomllib.loads((root/'Cargo.lock').read_text())['package'] if p['name'] == 'url')
tests = r'''
#[test]
fn vynx_and_upstream_service_classification() {
    for url in ["https://vynx.com.tr/", "https://DESK-API.VYNX.COM.TR/v1", "desk-relay.vynx.com.tr:21117", "https://rustdesk.com/"] {
        assert!(is_public(url), "expected public service domain: {url}");
    }
}
#[test]
fn lookalikes_userinfo_and_unrelated_domains_are_not_public_services() {
    for url in ["https://vynx.com.tr.evil.test/", "https://vynx.com.tr@evil.test/", "https://not-vynx.com.tr/", "https://vynxdesk.com/", "https://rustdesk.com@evil.test/"] {
        assert!(!is_public(url), "unexpected public service domain: {url}");
    }
}
'''
with tempfile.TemporaryDirectory(prefix='vynx-domain-probe-') as d:
    d = Path(d); (d/'src').mkdir()
    (d/'Cargo.toml').write_text('[package]\nname="vynx-domain-probe"\nversion="0.0.0"\nedition="2021"\n[dependencies]\nurl="=' + version + '"\n')
    (d/'src/lib.rs').write_text(body + tests)
    raise SystemExit(subprocess.run(['cargo', 'test', '--manifest-path', str(d/'Cargo.toml')]).returncode)
