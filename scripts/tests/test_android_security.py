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
        data[:6] = b'\x7fELF\x02\x01'
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


if __name__ == '__main__':
    unittest.main()
