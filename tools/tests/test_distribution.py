import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import catalog
import manage


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()


class CatalogTests(unittest.TestCase):
    def test_both_italian_plural_forms_required(self):
        valid = 'msgid "car"\nmsgid_plural "cars"\nmsgstr[0] "auto"\nmsgstr[1] "auto"\n'
        catalog.validate(valid)
        for invalid in [valid.replace('msgstr[1] "auto"', ''), valid.replace('msgstr[0] "auto"', 'msgstr[0] ""')]:
            with self.assertRaises(ValueError): catalog.validate(invalid)

    def test_overlay_preserves_stable_catalog_and_applies_italian(self):
        base = 'msgid "old"\nmsgstr "vecchio"\n\nmsgid "Speed"\nmsgstr ""\n'
        patch = 'msgid "Speed"\nmsgstr "Velocità"\n\nmsgid "dev-only"\nmsgstr "sviluppo"\n'
        result = catalog.overlay(base, patch)
        self.assertIn('msgstr "vecchio"', result)
        self.assertIn('msgstr "Velocità"', result)
        self.assertNotIn('dev-only', result)
        catalog.validate(result)

    def test_translation_loss_is_rejected(self):
        before = {'pack': {'strings': {'Speed': 'Velocità'}}}
        manage.preserve_translations(before, before)
        with self.assertRaises(ValueError): manage.preserve_translations(before, {'pack': {'strings': {}}})


class SubtreeTests(unittest.TestCase):
    def test_future_custom_release_updates_only_custom_subtree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, 'init', '-b', 'app')
            git(root, 'config', 'user.name', 'Test')
            git(root, 'config', 'user.email', 'test@example.invalid')
            (root / 'app.txt').write_text('application')
            git(root, 'add', '.')
            git(root, 'commit', '-m', 'app base')
            app = git(root, 'rev-parse', 'HEAD')
            git(root, 'checkout', '--orphan', 'custom')
            git(root, 'rm', '-rf', '.')
            (root / 'chart.txt').write_text('original')
            git(root, 'add', '.')
            git(root, 'commit', '-m', 'custom base')
            custom = git(root, 'rev-parse', 'HEAD')
            git(root, 'checkout', 'app')
            git(root, 'read-tree', '--prefix=custom/', '-u', custom)
            tree = git(root, 'write-tree')
            merged = git(root, 'commit-tree', tree, '-p', app, '-p', custom, '-m', 'unify')
            git(root, 'checkout', '--detach', merged)
            git(root, 'checkout', 'custom')
            (root / 'chart.txt').write_text('updated release')
            git(root, 'add', '.')
            git(root, 'commit', '-m', 'custom release')
            release = git(root, 'rev-parse', 'HEAD')
            git(root, 'checkout', '--detach', merged)
            self.assertTrue(manage.merge_release(root, custom, release, 'custom'))
            self.assertEqual((root / 'app.txt').read_text(), 'application')
            self.assertEqual((root / 'custom/chart.txt').read_text(), 'updated release')
            self.assertFalse((root / 'chart.txt').exists())
            self.assertTrue(manage.ancestor(root, merged, 'HEAD'))

    def test_concurrent_main_update_blocks_push(self):
        with patch.object(manage, 'git', return_value='new-sha\trefs/heads/main'):
            with self.assertRaisesRegex(RuntimeError, 'Concurrent main update'):
                manage.publish(Path('.'), 'original-sha')


if __name__ == '__main__':
    unittest.main()
