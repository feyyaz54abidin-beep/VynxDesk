import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BrandTests(unittest.TestCase):
    def test_client_has_no_unowned_account_fallback(self):
        self.assertNotIn('admin.vynxdesk.com', (ROOT / 'src/common.rs').read_text())

    def test_product_privacy_and_pricing_do_not_point_upstream(self):
        paths = ['desktop/pages/desktop_setting_page.dart', 'desktop/pages/install_page.dart',
                 'mobile/pages/settings_page.dart', 'desktop/pages/connection_page.dart']
        for path in paths:
            text = (ROOT / 'flutter/lib' / path).read_text()
            self.assertNotIn('https://rustdesk.com/privacy.html', text)
            self.assertNotIn('https://rustdesk.com/pricing', text)

    def test_branded_updater_returns_before_upstream_fingerprint_request(self):
        text = (ROOT / 'src/common.rs').read_text()
        start = text.index('pub async fn do_check_software_update()')
        call = text.index('hbb_common::version_check_request', start)
        self.assertIn('if !is_rustdesk()', text[start:call])
        self.assertIn('return Ok(())', text[start:call])

    def test_brand_profile_and_generated_links_agree(self):
        script = ROOT / 'scripts/vynx_brand.py'
        self.assertTrue(script.exists(), 'brand generator is missing')
        p = subprocess.run([sys.executable, str(script), '--check'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_profile_rejects_credentials_and_lookalike_domains(self):
        profile = ROOT / 'ops/vynx/brand.json'
        self.assertTrue(profile.exists(), 'brand profile is missing')
        original = json.loads(profile.read_text())
        for url in ['http://vynx.com.tr/', 'https://vynx.com.tr.evil.test/',
                    'https://vynx.com.tr@evil.test/', 'https://u:p@vynx.com.tr/',
                    'https://vynx.com.tr:444/', 'https://VYNX.com.tr/']:
            with self.subTest(url=url), tempfile.TemporaryDirectory() as d:
                data = dict(original); data['website'] = url
                path = Path(d) / 'brand.json'; path.write_text(json.dumps(data))
                p = subprocess.run([sys.executable, str(ROOT/'scripts/vynx_brand.py'), '--profile', str(path), '--check'], capture_output=True, text=True)
                self.assertNotEqual(p.returncode, 0)
                self.assertNotIn('u:p@', p.stdout + p.stderr)
