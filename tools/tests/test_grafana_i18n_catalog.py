from __future__ import annotations

import json
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "grafana/i18n"))
import catalog


class GrafanaI18nCatalogTest(unittest.TestCase):
    def _dashboard(self, root: Path, title="Overview", panel_title="Battery Level") -> Path:
        dashboards = root / "dashboards"
        dashboards.mkdir()
        data = {
            "uid": "overview",
            "title": title,
            "templating": {"list": [{"name": "car", "label": "Car", "query": "SELECT id FROM cars"}]},
            "panels": [
                {
                    "id": 7,
                    "title": panel_title,
                    "description": "Current battery state",
                    "targets": [{"refId": "A", "rawSql": "SELECT level AS battery_level FROM positions"}],
                }
            ],
        }
        (dashboards / "overview.json").write_text(json.dumps(data), encoding="utf-8")
        return dashboards

    def test_extracts_contextual_keys_and_ignores_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._dashboard(Path(tmp))
            messages = catalog.extract_messages(source)
            self.assertEqual(messages["dashboard.overview.title"].source, "Overview")
            self.assertEqual(messages["dashboard.overview.panel[7].title"].source, "Battery Level")
            self.assertEqual(messages["dashboard.overview.templating.variable[car].label"].source, "Car")
            sources = {message.source for message in messages.values()}
            self.assertNotIn("SELECT id FROM cars", sources)
            self.assertFalse(any("SELECT level" in source for source in sources))

    def test_legacy_italian_pack_seeds_schema_two_without_losing_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._dashboard(Path(tmp))
            messages = catalog.extract_messages(source)
            pack = {
                "locale": "it",
                "dashboard_titles": {"overview": "Panoramica"},
                "strings": {"Battery Level": "Livello batteria", "Car": "Auto"},
                "passthrough": ["Current battery state"],
            }
            updated, stats = catalog.synchronize_catalog(pack, messages)
            self.assertEqual(updated["schema"], 2)
            self.assertEqual(updated["messages"]["dashboard.overview.title"]["translation"], "Panoramica")
            self.assertEqual(updated["messages"]["dashboard.overview.panel[7].title"]["translation"], "Livello batteria")
            self.assertEqual(updated["messages"]["dashboard.overview.templating.variable[car].label"]["translation"], "Auto")
            self.assertEqual(
                updated["messages"]["dashboard.overview.panel[7].description"]["status"],
                "passthrough",
            )
            self.assertEqual(stats["missing"], 0)

    def test_changed_upstream_source_marks_translation_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._dashboard(root, panel_title="Battery")
            messages = catalog.extract_messages(source)
            pack = {
                "schema": 2,
                "locale": "it",
                "messages": {
                    "dashboard.overview.panel[7].title": {
                        "source": "Battery Level",
                        "translation": "Livello batteria",
                        "status": "translated",
                    }
                },
            }
            updated, stats = catalog.synchronize_catalog(pack, messages)
            entry = updated["messages"]["dashboard.overview.panel[7].title"]
            self.assertEqual(entry["source"], "Battery")
            self.assertEqual(entry["translation"], "Livello batteria")
            self.assertEqual(entry["status"], "needs_review")
            self.assertEqual(stats["needs_review"], 1)

    def test_removed_context_is_retained_as_obsolete(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._dashboard(Path(tmp))
            messages = catalog.extract_messages(source)
            pack = {
                "schema": 2,
                "locale": "de",
                "messages": {
                    "dashboard.old.panel[99].title": {
                        "source": "Old",
                        "translation": "Alt",
                        "status": "translated",
                    }
                },
            }
            updated, stats = catalog.synchronize_catalog(pack, messages)
            self.assertIn("dashboard.old.panel[99].title", updated["obsolete_messages"])
            self.assertEqual(stats["obsolete"], 1)


if __name__ == "__main__":
    unittest.main()
