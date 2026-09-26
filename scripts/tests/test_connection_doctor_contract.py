"""Source wiring and localization contracts, not native/device acceptance."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]

class DoctorContractTests(unittest.TestCase):
    def test_existing_observer_delivers_to_feature_and_session_start_resets(self):
        model = (ROOT / 'flutter/lib/models/model.dart').read_text()
        body = model.split('updateConnectionInsight(Map<String, dynamic> evt) {', 1)[1].split('class RecordingModel', 1)[0]
        self.assertIn('connectionDoctor.ingest(', body)
        self.assertIn('connectionDoctor.reset();', body)
        start = model.split('  void start(\n    String id,', 1)[1].split('    assert(', 1)[0]
        self.assertIn('qualityMonitorModel.connectionDoctor.reset();', start)

    def test_existing_session_dialog_hosts_shared_entry(self):
        overlay = (ROOT / 'flutter/lib/common/widgets/overlay.dart').read_text()
        self.assertIn('ConnectionDoctorButton(', overlay)
        self.assertIn('ConnectionDoctorPanel', (ROOT / 'flutter/lib/features/connection_doctor/panel.dart').read_text())
        self.assertIn("tag: 'vynx-connection-doctor'", overlay)

    def test_feature_has_no_remote_or_filesystem_side_effects(self):
        feature = ROOT / 'flutter/lib/features/connection_doctor'
        code = '\n'.join(p.read_text() for p in feature.glob('*.dart'))
        for forbidden in ['dart:io', 'package:http', 'generated_bridge', 'bind.', 'launchUrl', 'File(']:
            self.assertNotIn(forbidden, code)
        self.assertEqual(code.count('Clipboard.setData('), 1)
        self.assertIn('Timer.periodic', code)
        self.assertIn('_timer.cancel();', code)

    def test_feature_text_keys_exist_in_all_locales(self):
        keys = (ROOT / 'docs/CONNECTION_DOCTOR_KEYS.txt').read_text().splitlines()
        self.assertGreater(len(keys), 20)
        for locale in (ROOT / 'src/lang').glob('*.rs'):
            text = locale.read_text()
            for key in keys:
                self.assertIn('("' + key + '",', text, f'{locale.name}: {key}')
        tr = (ROOT / 'src/lang/tr.rs').read_text()
        for key in keys:
            self.assertNotIn('("' + key + '", "")', tr)

if __name__ == '__main__': unittest.main()
