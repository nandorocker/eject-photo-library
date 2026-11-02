"""Check the actual release contents and reproducibility, without running eject."""

from pathlib import Path
import hashlib
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def test_self_contained_workflow(self):
        with zipfile.ZipFile(ROOT / 'dist/Eject.Photo.Library.alfredworkflow') as bundle:
            self.assertIsNone(bundle.testzip())
            self.assertEqual(set(bundle.namelist()), {
                'info.plist', 'icon.png', 'eject-photo-library.zsh',
                'alfred-launcher.zsh', 'alfred-list.zsh', 'README.md', 'LICENSE',
            })
            info = plistlib.loads(bundle.read('info.plist'))
            self.assertEqual(info['createdby'], 'nando rossi')
            self.assertEqual(info['webaddress'], 'https://nan.do')
            self.assertIn('https://buymeacoffee.com/nandorossi', info['readme'])
            self.assertFalse(info['disabled'])
            inputs = [o for o in info['objects'] if o['type'] == 'alfred.workflow.input.scriptfilter']
            self.assertEqual(len(inputs), 1)
            self.assertEqual(inputs[0]['config']['keyword'], 'ejp')
            self.assertEqual(inputs[0]['config']['argumenttype'], 2)
            for name in ('alfred-list.zsh', 'alfred-launcher.zsh', 'eject-photo-library.zsh'):
                self.assertEqual((bundle.getinfo(name).external_attr >> 16) & 0o777, 0o755)
            self.assertEqual(bundle.read('eject-photo-library.zsh'), (ROOT / 'src/eject-photo-library.zsh').read_bytes())

    def test_build_is_deterministic(self):
        files = ('Eject.Photo.Library.alfredworkflow', 'Eject.Photo.Library.command', 'SHA256SUMS')
        before = {name: (ROOT / 'dist' / name).read_bytes() for name in files}
        subprocess.run([sys.executable, str(ROOT / 'scripts/build.py')], check=True, capture_output=True)
        self.assertEqual(before, {name: (ROOT / 'dist' / name).read_bytes() for name in files})

    def test_checksums(self):
        for line in (ROOT / 'dist/SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            self.assertEqual(digest, hashlib.sha256((ROOT / 'dist' / name).read_bytes()).hexdigest())

    def test_failed_action_becomes_useful_notification(self):
        with tempfile.TemporaryDirectory(prefix='photo-library-notification-test-') as directory:
            root = Path(directory)
            (root / 'alfred-launcher.zsh').write_bytes((ROOT / 'workflow/alfred-launcher.zsh').read_bytes())
            (root / 'eject-photo-library.zsh').write_text(
                "#!/bin/zsh\nprint 'Please finish work and quit Photos (PID 99999), then run this again.'\nexit 1\n"
            )
            result = subprocess.run(['/bin/zsh', '-f', str(root / 'alfred-launcher.zsh'), '/example/Library.dmg'],
                env={**os.environ, 'alfred_workflow_cache': str(root / 'cache')},
                text=True, capture_output=True, check=True, timeout=10)
            self.assertIn('Could not eject. Please finish work and quit Photos', result.stdout)
            self.assertEqual((root / 'cache/last-run.log').stat().st_mode & 0o777, 0o600)

    def test_missing_selection_does_not_run_eject(self):
        with tempfile.TemporaryDirectory(prefix='photo-library-selection-test-') as directory:
            root = Path(directory)
            (root / 'alfred-launcher.zsh').write_bytes((ROOT / 'workflow/alfred-launcher.zsh').read_bytes())
            result = subprocess.run(['/bin/zsh', '-f', str(root / 'alfred-launcher.zsh')],
                text=True, capture_output=True, check=True, timeout=10)
            self.assertIn('Choose a mounted photo library image', result.stdout)
            self.assertNotIn('no such file', result.stderr)

    def test_list_failure_is_an_inactive_alfred_result(self):
        with tempfile.TemporaryDirectory(prefix='photo-library-list-test-') as directory:
            root = Path(directory)
            (root / 'alfred-list.zsh').write_bytes((ROOT / 'workflow/alfred-list.zsh').read_bytes())
            (root / 'eject-photo-library.zsh').write_text('#!/bin/zsh\nexit 1\n')
            result = subprocess.run(['/bin/zsh', '-f', str(root / 'alfred-list.zsh')],
                text=True, capture_output=True, check=True, timeout=10)
            self.assertFalse(json.loads(result.stdout)['items'][0]['valid'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
