"""Check the workflow contract, including consumers of optional legacy artifacts."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load((ROOT / '.github/workflows/flutter-build.yml').read_text())
        self.jobs = self.workflow['jobs']

    def test_legacy_windows_is_explicit_opt_in(self):
        trigger = self.workflow.get('on', self.workflow.get(True))
        self.assertIs(trigger['workflow_call']['inputs']['build-legacy-windows-sciter']['default'], False)
        self.assertIn('inputs.build-legacy-windows-sciter', self.jobs['build-for-windows-sciter']['if'])
        self.assertEqual(self.workflow['env']['SCITER_RUST_VERSION'], '1.75')

    def test_both_windows_flutter_builds_include_profiles(self):
        jobs = self.jobs['build-for-windows-flutter']['strategy']['matrix']['job']
        self.assertEqual({job['arch'] for job in jobs}, {'x86_64', 'aarch64'})
        for job in jobs:
            self.assertIn('--windows-input-plus', job['build-args'])

    def test_skipped_legacy_build_does_not_cancel_supported_packaging(self):
        job = self.jobs['publish_unsigned']
        self.assertIn('!cancelled()', job['if'])
        self.assertIn("needs.build-for-windows-flutter.result == 'success'", job['if'])
        self.assertIn('!inputs.build-legacy-windows-sciter', job['if'])
        step = next(step for step in job['steps'] if step.get('with', {}).get('name') == 'rustdesk-unsigned-windows-x86')
        self.assertIn('inputs.build-legacy-windows-sciter', step['if'])

    def test_published_artifacts_still_require_validated_identity(self):
        steps = self.jobs['validate-release-identity']['steps']
        check = next(step for step in steps if step['name'] == 'Require protected production identity for artifacts')
        self.assertIn('inputs.upload-artifact', check['if'])
        self.assertIn('require_release_environment', check['run'])
        self.assertNotIn('continue-on-error', check)

if __name__ == '__main__':
    unittest.main()
