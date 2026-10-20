from __future__ import annotations

import json
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "i18n"))

import catalog
import generate


class I18nTest(unittest.TestCase):
    def _dashboard(self, root: Path, title="Overview", panel_title="Battery Level") -> Path:
        source = root / "dashboards"
        source.mkdir()
        data = {
            "uid": "overview",
            "title": title,
            "tags": ["TeslamateCustomDashboards"],
            "templating": {
                "list": [
                    {"name": "car", "label": "Car", "query": "SELECT id FROM cars"}
                ]
            },
            "links": [{"title": "Details", "url": "/d/details/something"}],
            "panels": [
                {
                    "id": 7,
                    "title": panel_title,
                    "description": "Current battery state",
                    "targets": [
                        {
                            "refId": "A",
                            "rawSql": "SELECT level AS battery_level FROM positions",
                        }
                    ],
                }
            ],
        }
        (source / "overview.json").write_text(json.dumps(data), encoding="utf-8")
        details = {
            "uid": "details",
            "title": "Details",
            "tags": ["TeslamateCustomDashboards"],
            "panels": [],
        }
        (source / "details.json").write_text(json.dumps(details), encoding="utf-8")
        return source

    def test_extracts_context_and_never_extracts_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._dashboard(Path(tmp))
            messages = catalog.extract_messages(source)
            self.assertEqual(messages["dashboard.overview.title"].source, "Overview")
            self.assertEqual(messages["dashboard.overview.panel[7].title"].source, "Battery Level")
            self.assertEqual(
                messages["dashboard.overview.templating.variable[car].label"].source,
                "Car",
            )
            sources = {m.source for m in messages.values()}
            self.assertNotIn("SELECT id FROM cars", sources)
            self.assertFalse(any("SELECT level" in source for source in sources))

    def test_legacy_pack_migrates_without_losing_translations(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._dashboard(Path(tmp))
            messages = catalog.extract_messages(source)
            pack = {
                "locale": "it",
                "dashboard_titles": {"overview": "Panoramica"},
                "strings": {
                    "Battery Level": "Livello batteria",
                    "Car": "Auto",
                    "Details": "Dettagli",
                },
                "passthrough": ["Current battery state"],
            }
            updated, stats = catalog.synchronize_catalog(pack, messages)
            self.assertEqual(updated["schema"], 2)
            self.assertEqual(
                updated["messages"]["dashboard.overview.title"]["translation"],
                "Panoramica",
            )
            self.assertEqual(
                updated["messages"]["dashboard.overview.panel[7].title"]["translation"],
                "Livello batteria",
            )
            self.assertGreaterEqual(stats["translated"], 3)

    def test_source_change_marks_context_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._dashboard(Path(tmp), panel_title="Battery")
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

    def test_generator_is_language_agnostic_and_preserves_sql(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._dashboard(root)
            output = root / "out"
            translations = root / "locales"
            translations.mkdir()
            (translations / "de.json").write_text(
                json.dumps(
                    {
                        "locale": "de",
                        "dashboard_titles": {"overview": "Übersicht", "details": "Details"},
                        "strings": {
                            "Battery Level": "Batteriestand",
                            "Car": "Auto",
                            "Details": "Details",
                        },
                    }
                ),
                encoding="utf-8",
            )
            generate.generate_locale(source, translations / "de.json", output)
            localized = json.loads((output / "de" / "overview.json").read_text())
            self.assertEqual(localized["title"], "Übersicht")
            self.assertEqual(localized["panels"][0]["title"], "Batteriestand")
            self.assertEqual(
                localized["panels"][0]["targets"][0]["rawSql"],
                "SELECT level AS battery_level FROM positions",
            )
            self.assertEqual(localized["uid"], "overview-de")
            self.assertEqual(localized["links"][0]["url"], "/d/details-de/something")
            self.assertIn("TeslamateCustomDashboards-de", localized["tags"])

    def test_context_override_beats_legacy_source_translation(self):
        pack = {
            "schema": 2,
            "locale": "it",
            "strings": {"State": "Stato"},
            "messages": {
                "dashboard.overview.panel[7].title": {
                    "source": "State",
                    "translation": "Condizione",
                    "status": "translated",
                }
            },
        }
        self.assertEqual(
            catalog.resolve_translation(
                pack,
                "dashboard.overview.panel[7].title",
                "State",
                "overview",
            ),
            "Condizione",
        )


if __name__ == "__main__":
    unittest.main()
