import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
import yaml

ROOT = Path(__file__).resolve().parents[2]
ANDROID = '{http://schemas.android.com/apk/res/android}'


class AndroidSourceTests(unittest.TestCase):
    def setUp(self):
        self.manifest = ET.parse(ROOT / 'flutter/android/app/src/main/AndroidManifest.xml').getroot()

    def test_remote_credentials_not_backed_up(self):
        app = self.manifest.find('application')
        self.assertEqual(app.get(ANDROID + 'allowBackup'), 'false')
        self.assertEqual(app.get(ANDROID + 'fullBackupContent'), '@xml/backup_rules')
        self.assertEqual(app.get(ANDROID + 'dataExtractionRules'), '@xml/data_extraction_rules')

    def test_no_release_debug_boot_action(self):
        self.assertFalse(any('DEBUG_BOOT' in x.get(ANDROID + 'name', '') for x in self.manifest.iter('action')))
        source = (ROOT / 'flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/BootReceiver.kt').read_text()
        self.assertIn('BuildConfig.DEBUG && DEBUG_BOOT_COMPLETED', source)

    def test_auxiliary_components_not_exported(self):
        app = self.manifest.find('application')
        for name in ['.FloatingWindowService', '.PermissionRequestTransparentActivity']:
            match = next(x for x in app if x.get(ANDROID + 'name') == name)
            self.assertEqual(match.get(ANDROID + 'exported'), 'false')

    def test_no_automatic_unsigned_apk_publication(self):
        data = yaml.safe_load((ROOT / '.github/workflows/flutter-build.yml').read_text())
        for jobname in ['build-rustdesk-android', 'build-rustdesk-android-universal']:
            steps = data['jobs'][jobname]['steps']
            self.assertFalse(any(s.get('name') == 'Publish unsigned apk package' for s in steps))
            gate = next(s for s in steps if s.get('name') == 'Verify customer APK identity')
            self.assertIn('check_android_apk.py', gate['run'])
            self.assertIn('UPLOAD_ARTIFACT', gate['if'])
            gate_index = steps.index(gate)
            for i, step in enumerate(steps):
                if step.get('name') == 'Publish signed apk package':
                    self.assertGreater(i, gate_index)


class ApkGateTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / 'scripts/check_android_apk.py'
        spec = importlib.util.spec_from_file_location('apk_gate', path)
        self.gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.gate)

    def xml(self, extra=''):
        return f'<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.vynxdesk.client"><application android:allowBackup="false" {extra}/></manifest>'

    def test_release_manifest_passes(self):
        self.gate.validate_manifest(self.xml())

    def test_debuggable_and_test_only_rejected(self):
        for field in ['debuggable', 'testOnly']:
            with self.assertRaises(ValueError):
                self.gate.validate_manifest(self.xml(f'android:{field}="true"'))

    def test_wrong_package_and_enabled_backup_rejected(self):
        for xml in [self.xml().replace('com.vynxdesk.client', 'com.fake.app'), self.xml().replace('allowBackup="false"', 'allowBackup="true"')]:
            with self.assertRaises(ValueError):
                self.gate.validate_manifest(xml)

    def test_signature_requires_explicit_expected_fingerprint(self):
        report = 'Verified using v2 scheme (APK Signature Scheme v2): true\nSigner #1 certificate DN: CN=VYNX\nSigner #1 certificate SHA-256 digest: ' + 'a' * 64
        self.gate.validate_signer(report, 'a' * 64)
        for fp in ['', 'b' * 64]:
            with self.assertRaises(ValueError):
                self.gate.validate_signer(report, fp)

    def test_debug_certificate_rejected_even_if_fingerprint_matches(self):
        report = 'Verified using v2 scheme (APK Signature Scheme v2): true\nSigner #1 certificate DN: CN=Android Debug, O=Android\nSigner #1 certificate SHA-256 digest: ' + 'a' * 64
        with self.assertRaises(ValueError):
            self.gate.validate_signer(report, 'a' * 64)

    def test_multiple_signers_rejected(self):
        report = 'Verified using v2 scheme (APK Signature Scheme v2): true\nSigner #1 certificate SHA-256 digest: ' + 'a' * 64 + '\nSigner #2 certificate SHA-256 digest: ' + 'b' * 64
        with self.assertRaises(ValueError):
            self.gate.validate_signer(report, 'a' * 64)

    def elf(self, alignment=16384):
        import struct
        data = bytearray(120)
        data[:7] = b'\x7fELF\x02\x01\x01'
        struct.pack_into('<HHI', data, 16, 3, 183, 1)
        struct.pack_into('<Q', data, 32, 64)
        struct.pack_into('<HH', data, 54, 56, 1)
        struct.pack_into('<I', data, 64, 1)
        struct.pack_into('<Q', data, 112, alignment)
        return bytes(data)

    def test_elf_headers_checked_not_file_name(self):
        self.assertEqual(self.gate.elf_load_alignments(self.elf()), [16384])
        for data in [b'bad', self.elf()[:100], self.elf().replace(b'ELF', b'BAD')]:
            with self.assertRaises(ValueError):
                self.gate.elf_load_alignments(data)

    def test_real_zip_requires_all_native_runtime_files(self):
        import tempfile, zipfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / 'candidate.apk'
            with zipfile.ZipFile(apk, 'w') as archive:
                archive.writestr('lib/arm64-v8a/librustdesk.so', self.elf())
            with self.assertRaisesRegex(ValueError, 'Missing runtime'):
                self.gate.inspect_native(apk, True)
            with zipfile.ZipFile(apk, 'a') as archive:
                for name in ['libflutter.so', 'libapp.so']:
                    archive.writestr('lib/arm64-v8a/' + name, self.elf())
            self.assertEqual(len(self.gate.inspect_native(apk, True)), 3)

    def test_native_4kb_library_cannot_claim_16kb_support(self):
        import tempfile, zipfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / 'candidate.apk'
            with zipfile.ZipFile(apk, 'w') as archive:
                for name in ['librustdesk.so', 'libflutter.so', 'libapp.so']:
                    archive.writestr('lib/arm64-v8a/' + name, self.elf(4096))
            with self.assertRaisesRegex(ValueError, '16 KB'):
                self.gate.inspect_native(apk, True)

    def native_apk(self, data, abi='arm64-v8a'):
        import tempfile, zipfile
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        apk = Path(temp.name) / 'candidate.apk'
        with zipfile.ZipFile(apk, 'w') as archive:
            for name in ['librustdesk.so', 'libflutter.so', 'libapp.so']:
                archive.writestr(f'lib/{abi}/{name}', data)
        return apk

    def test_wrong_machine_cannot_pass_as_arm64(self):
        import struct
        data = bytearray(self.elf())
        struct.pack_into('<H', data, 18, 62)  # Real x86-64 header, mislabeled ARM64 path.
        with self.assertRaisesRegex(ValueError, 'ABI'):
            self.gate.inspect_native(self.native_apk(data), True)
        self.assertEqual(len(self.gate.inspect_native(self.native_apk(data, 'x86_64'), True)), 3)

    def test_unknown_abi_directory_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ABI'):
            self.gate.inspect_native(self.native_apk(self.elf(), 'imaginary-cpu'), True)

    def test_segment_alignment_is_a_power_of_two_even_without_16kb_gate(self):
        with self.assertRaisesRegex(ValueError, 'alignment'):
            self.gate.inspect_native(self.native_apk(self.elf(12345)))

    def test_nonshared_elf_is_rejected(self):
        import struct
        data = bytearray(self.elf())
        struct.pack_into('<H', data, 16, 2)
        with self.assertRaisesRegex(ValueError, 'shared'):
            self.gate.inspect_native(self.native_apk(data))

    def test_load_segment_offset_and_address_must_be_congruent(self):
        import struct
        data = bytearray(self.elf())
        struct.pack_into('<Q', data, 80, 1)  # p_vaddr != p_offset mod p_align
        with self.assertRaisesRegex(ValueError, 'alignment'):
            self.gate.inspect_native(self.native_apk(data), True)

    def test_load_segment_cannot_read_past_file(self):
        import struct
        data = bytearray(self.elf())
        struct.pack_into('<QQ', data, 96, len(data) + 1, len(data) + 1)
        with self.assertRaisesRegex(ValueError, 'segment'):
            self.gate.inspect_native(self.native_apk(data))

    def test_internal_android_components_cannot_be_exported(self):
        for tag, name in [('service', 'MainService'), ('service', 'FloatingWindowService'),
                          ('activity', 'PermissionRequestTransparentActivity')]:
            for prefix in ('.', 'com.carriez.flutter_hbb.'):
                xml = self.xml().replace('/></manifest>',
                    f'><{tag} android:name="{prefix}{name}" android:exported="true"/></application></manifest>')
                with self.subTest(name=name, prefix=prefix), self.assertRaisesRegex(ValueError, 'exported'):
                    self.gate.validate_manifest(xml)
                self.gate.validate_manifest(xml.replace('exported="true"', 'exported="false"'))

    def test_accessibility_service_requires_its_system_permission(self):
        xml = self.xml().replace('/></manifest>',
            '><service android:name=".InputService" android:exported="false"/></application></manifest>')
        with self.assertRaisesRegex(ValueError, 'permission'):
            self.gate.validate_manifest(xml)
        self.gate.validate_manifest(xml.replace('android:exported="false"',
            'android:exported="false" android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"'))


if __name__ == '__main__':
    unittest.main()
