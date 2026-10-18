"""Regression tests for real Git merges, failures and safe publication."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sync_italian_localization as sync
import generate_localized_dashboards as generator


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()


class GitSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init", "-b", "main")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "config", "user.email", "test@example.invalid")
        (self.root / "dashboard").write_text("base\n")
        self.base = self.commit("baseline")
        git(self.root, "checkout", "-b", "italian")
        (self.root / "translations").write_text("italiano\n")
        self.localized = self.commit("translations")
        git(self.root, "checkout", "main")
        (self.root / "upstream-new").write_text("new dashboard\n")
        self.latest = self.commit("new release")
        git(self.root, "checkout", "italian")

    def commit(self, message):
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", message)
        return git(self.root, "rev-parse", "HEAD")

    def test_new_release_merges_without_rewriting_localization(self):
        self.assertTrue(sync.merge_release(self.root, self.base, self.latest))
        self.assertTrue(sync.ancestor(self.root, self.localized, "HEAD"))
        self.assertTrue(sync.ancestor(self.root, self.latest, "HEAD"))
        self.assertEqual((self.root / "translations").read_text(), "italiano\n")
        self.assertTrue((self.root / "upstream-new").exists())

    def test_already_integrated_is_idempotent(self):
        self.assertFalse(sync.merge_release(self.root, self.base, self.base))
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), self.localized)

    def test_conflict_aborts_without_changing_original_head(self):
        (self.root / "dashboard").write_text("italian edit\n")
        head = self.commit("local edit")
        git(self.root, "checkout", "main")
        (self.root / "dashboard").write_text("upstream edit\n")
        release = self.commit("upstream edit")
        git(self.root, "checkout", "italian")
        with self.assertRaisesRegex(RuntimeError, "merge conflict"):
            sync.merge_release(self.root, self.base, release)
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), head)
        self.assertEqual(git(self.root, "status", "--porcelain"), "")
        self.assertEqual((self.root / "dashboard").read_text(), "italian edit\n")

    def test_release_regression_blocks_merge(self):
        with self.assertRaisesRegex(RuntimeError, "regressed"):
            sync.merge_release(self.root, self.latest, self.base)
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), self.localized)

    def test_missing_recorded_base_blocks_merge(self):
        with self.assertRaisesRegex(RuntimeError, "recorded Customs baseline"):
            sync.merge_release(self.root, self.latest, self.latest)

    def remote(self):
        remote = Path(self.tmp.name) / "remote.git"
        subprocess.check_call(["git", "init", "--bare", str(remote)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        git(self.root, "remote", "add", "origin", str(remote))
        git(self.root, "push", "origin", "HEAD:refs/heads/italian")
        return remote

    def test_publish_fast_forwards_and_keeps_history(self):
        remote = self.remote()
        sync.merge_release(self.root, self.base, self.latest)
        candidate = git(self.root, "rev-parse", "HEAD")
        sync.publish(self.root, "italian", self.localized)
        self.assertEqual(git(remote, "rev-parse", "refs/heads/italian"), candidate)
        self.assertTrue(sync.ancestor(self.root, self.localized, candidate))

    def test_concurrent_remote_update_is_preserved(self):
        remote = self.remote()
        (self.root / "concurrent").write_text("user work\n")
        concurrent = self.commit("concurrent user commit")
        git(self.root, "push", "origin", "HEAD:refs/heads/italian")
        git(self.root, "checkout", "--detach", self.localized)
        sync.merge_release(self.root, self.base, self.latest)
        with self.assertRaisesRegex(RuntimeError, "Concurrent branch update"):
            sync.publish(self.root, "italian", self.localized)
        self.assertEqual(git(remote, "rev-parse", "refs/heads/italian"), concurrent)


class LocalizationTests(unittest.TestCase):
    def test_existing_translations_cannot_disappear_or_change(self):
        before = {"strings": {"Speed": "Velocità"}, "dashboard_titles": {"a": "Titolo"}, "passthrough": ["Tesla"]}
        sync.preserve_pack(before, before)
        for after in ({}, {**before, "strings": {"Speed": "Altro"}}, {**before, "passthrough": []}):
            with self.assertRaises(RuntimeError):
                sync.preserve_pack(before, after)

    def test_sensitive_paths_cover_old_and_new_repository_layouts(self):
        for name in ("priv/repo/migrations/a.exs", "elixir/priv/repo/migrations/a.exs",
                     "grafana/dashboards/a.json", "grafana/provisioning/datasource.yml",
                     "grafana/Dockerfile", "Dockerfile", "docker-compose.yml",
                     "compose.yaml", "scripts/docker-compose.yml", "elixir/mix.lock",
                     "elixir/config/runtime.exs", "entrypoint.sh", "website/docs/installation/docker.md"):
            with self.subTest(path=name):
                self.assertRegex(name, sync.SENSITIVE)
        self.assertNotRegex("README.md", sync.SENSITIVE)

    def test_real_dashboard_pack_and_generation(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/validate_localization.py")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(ROOT / "scripts/generate_localized_dashboards.py"),
                                     "--source", str(ROOT / "dashboards"), "--pack", str(ROOT / "i18n/it.json"),
                                     "--output", tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual({p.name for p in Path(tmp).glob("*.json")},
                             {p.name for p in (ROOT / "dashboards").glob("*.json")})

    def test_alias_references_and_technical_values(self):
        source = {"uid": "keep", "title": "Speed", "panels": [{"title": "Speed", "targets": [
            {"rawSql": 'SELECT speed AS "Speed" FROM positions', "refId": "A"}],
            "fieldConfig": {"overrides": [{"matcher": {"id": "byName", "options": "Speed"}}]}}],
            "templating": {"list": [{"name": "Speed", "query": "SELECT speed FROM positions", "current": {"value": "Speed"}}]}}
        result = generator.localize_dashboard(source, "speed", {"strings": {"Speed": "Velocità"}})
        self.assertEqual(result["uid"], "keep")
        self.assertEqual(result["templating"], source["templating"])
        self.assertEqual(result["panels"][0]["fieldConfig"]["overrides"][0]["matcher"]["options"], "Velocità")
        self.assertIn('AS "Velocità"', result["panels"][0]["targets"][0]["rawSql"])

    def test_tag_rewrite_is_rejected(self):
        with patch.object(sync, "run"), patch.object(sync, "git", return_value="new-sha"):
            with self.assertRaisesRegex(RuntimeError, "tag moved"):
                sync.previous_sha(Path("."), {"teslamate_release": "v1", "teslamate_commit": "old-sha"},
                                  "owner/repo", "teslamate", "teslamate")


if __name__ == "__main__":
    unittest.main()
