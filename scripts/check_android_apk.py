#!/usr/bin/env python3
"""Inspect a real customer APK using Android SDK verification tools.

Not an on-device security test. No success without a supplied publisher fingerprint.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ANDROID = '{http://schemas.android.com/apk/res/android}'


def validate_manifest(text):
    root = ET.fromstring(text)
    if root.get('package') != 'com.vynxdesk.client':
        raise ValueError('Unexpected application ID')
    app = root.find('application')
    if app is None or app.get(ANDROID + 'allowBackup') != 'false':
        raise ValueError('Application backup must be explicitly disabled')
    for key in ('debuggable', 'testOnly'):
        if app.get(ANDROID + key, 'false').lower() != 'false':
            raise ValueError(f'Customer APK is {key}')
    if any('DEBUG_BOOT' in action.get(ANDROID + 'name', '') for action in root.iter('action')):
        raise ValueError('Debug boot action leaked into customer APK')


def validate_signer(report, expected):
    expected = expected.replace(':', '').strip().lower()
    if not re.fullmatch(r'[a-f0-9]{64}', expected):
        raise ValueError('A SHA-256 publisher certificate fingerprint is required')
    digests = re.findall(r'^Signer #\d+ certificate SHA-256 digest:\s*([a-fA-F0-9]+)\s*$', report, re.M)
    if len(digests) != 1 or digests[0].lower() != expected:
        raise ValueError('Publisher certificate mismatch or unexpected multiple signers')
    if re.search(r'CN\s*=\s*Android Debug', report, re.I):
        raise ValueError('Android debug certificate is not a customer identity')
    if not re.search(r'Verified using v[23](?:\.1)? scheme[^\n]*:\s*true', report):
        raise ValueError('APK requires a verified v2 or newer signature')


def elf_load_alignments(data):
    if len(data) < 64 or data[:4] != b'\x7fELF' or data[5] not in (1, 2):
        raise ValueError('Malformed native ELF library')
    endian = '<' if data[5] == 1 else '>'
    if data[4] == 2:
        phoff = struct.unpack_from(endian + 'Q', data, 32)[0]
        entsize, count = struct.unpack_from(endian + 'HH', data, 54)
        minimum, alignment_offset, fmt = 56, 48, 'Q'
    elif data[4] == 1:
        phoff = struct.unpack_from(endian + 'I', data, 28)[0]
        entsize, count = struct.unpack_from(endian + 'HH', data, 42)
        minimum, alignment_offset, fmt = 32, 28, 'I'
    else:
        raise ValueError('Unknown ELF class')
    if entsize < minimum or count == 0 or count > 1024 or phoff + count * entsize > len(data):
        raise ValueError('Invalid ELF program headers')
    values = []
    for index in range(count):
        offset = phoff + index * entsize
        if struct.unpack_from(endian + 'I', data, offset)[0] == 1:
            values.append(struct.unpack_from(endian + fmt, data, offset + alignment_offset)[0])
    if not values:
        raise ValueError('ELF has no loadable segments')
    return values


def inspect_native(apk, require_16kb=False):
    result = {}
    with zipfile.ZipFile(apk) as archive:
        if len(archive.infolist()) > 30000 or sum(i.file_size for i in archive.infolist()) > 1024 * 1024 * 1024:
            raise ValueError('APK exceeds inspection limits')
        if archive.testzip() is not None:
            raise ValueError('Corrupt APK ZIP entry')
        files = archive.namelist()
        if len(files) != len(set(files)):
            raise ValueError('Duplicate APK ZIP entries')
        for info in archive.infolist():
            if info.filename.startswith('lib/') and info.filename.endswith('.so'):
                if info.file_size > 256 * 1024 * 1024:
                    raise ValueError('Native library exceeds inspection limit')
                alignments = elf_load_alignments(archive.read(info))
                result[info.filename] = min(alignments)
                if require_16kb and any(f'/{abi}/' in info.filename for abi in ('arm64-v8a', 'x86_64')):
                    if any(a < 16384 or a % 16384 for a in alignments):
                        raise ValueError(f'16 KB ELF alignment is missing: {info.filename}')
        abis = {name.split('/')[1] for name in result}
        if not abis:
            raise ValueError('No native libraries found')
        for abi in abis:
            for name in ['librustdesk.so', 'libflutter.so', 'libapp.so']:
                if f'lib/{abi}/{name}' not in result:
                    raise ValueError(f'Missing runtime library for {abi}: {name}')
    return result


def inspect(apk, fingerprint, apksigner, apkanalyzer, zipalign, require_16kb):
    # apksigner validates the actual APK, not a hash file supplied beside it.
    report = subprocess.run([apksigner, 'verify', '--verbose', '--print-certs', str(apk)],
                            check=True, capture_output=True, text=True, timeout=90).stdout
    validate_signer(report, fingerprint)
    manifest = subprocess.run([apkanalyzer, 'manifest', 'print', str(apk)],
                              check=True, capture_output=True, text=True, timeout=90).stdout
    validate_manifest(manifest)
    native = inspect_native(apk, require_16kb)
    if require_16kb:
        subprocess.run([zipalign, '-c', '-P', '16', '-v', '4', str(apk)],
                       check=True, capture_output=True, text=True, timeout=90)
    with open(apk, 'rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    return {'apk': apk.name, 'sha256': digest,
            'signature': 'verified-publisher', 'native_load_alignment': native,
            'page_size_16kb': 'checked' if require_16kb else 'not-checked',
            'device_acceptance': 'not-tested'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('apk', type=Path)
    p.add_argument('--fingerprint', required=True)
    p.add_argument('--apksigner', default='apksigner')
    p.add_argument('--apkanalyzer', default='apkanalyzer')
    p.add_argument('--zipalign', default='zipalign')
    p.add_argument('--require-16kb', action='store_true')
    args = p.parse_args()
    try:
        print(json.dumps(inspect(args.apk, args.fingerprint, args.apksigner, args.apkanalyzer,
                                 args.zipalign, args.require_16kb), indent=2))
    except (ValueError, OSError, subprocess.SubprocessError, ET.ParseError, zipfile.BadZipFile, struct.error) as exc:
        raise SystemExit(f'APK release gate failed: {type(exc).__name__}: {exc}') from None


if __name__ == '__main__':
    main()
