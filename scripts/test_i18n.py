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
import update_catalog
import validate_generated


class I18nTest(unittest.TestCase):
    def _dashboard(self, root: Path, title="Overview", panel_title="Battery Level", uid="overview") -> Path:
        source = root / "dashboards"
        source.mkdir(exist_ok=True)
        data = {
            "id": 42,
            "uid": uid,
            "title": title,
            "tags": ["TeslamateCustomDashboards"],
            "templating": {"list": [{"name": "car", "label": "Car", "query": "SELECT id FROM cars"}]},
            "links": [{"title": "Details", "url": "/d/details/something"}],
            "panels": [{
                "id": 7,
                "title": panel_title,
                "description": "Current battery state",
                "targets": [{"refId": "A", "rawSql": "SELECT level AS battery_level FROM positions WHERE car_id = $car_id"}],
            }],
        }
        (source / "overview.json").write_text(json.dumps(data), encoding="utf-8")
        (source / "details.json").write_text(json.dumps({
            "id": 43, "uid": "details", "title": "Details",
            "tags": ["TeslamateCustomDashboards"], "panels": [],
        }), encoding="utf-8")
        return source

    def test_extracts_context_and_never_extracts_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._dashboard(Path(tmp))
            messages = catalog.extract_messages(source)
            self.assertEqual(messages["dashboard.overview.title"].source, "Overview")
            self.assertEqual(messages["dashboard.overview.panel[7].title"].source, "Battery Level")
            self.assertEqual(messages["dashboard.overview.templating.variable[car].label"].source, "Car")
            sources = {m.source for m in messages.values()}
            self.assertNotIn("SELECT id FROM cars", sources)
            self.assertFalse(any("SELECT level" in source for source in sources))

    def test_repeated_generic_ids_get_unique_context_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._dashboard(Path(tmp))
            path = source / "overview.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["panels"][0]["transformations"] = [
                {"id": "calculateField", "options": {"alias": "avg_cost_kwh"}},
                {"id": "calculateField", "options": {"alias": "avg_cost_km_temp"}},
            ]
            path.write_text(json.dumps(data), encoding="utf-8")
            messages = catalog.extract_messages(source)
            self.assertEqual(
                messages["dashboard.overview.panel[7].transformations[0:id=calculateField].options.alias"].source,
                "avg_cost_kwh",
            )
            self.assertEqual(
                messages["dashboard.overview.panel[7].transformations[1:id=calculateField].options.alias"].source,
                "avg_cost_km_temp",
            )

    def test_legacy_pack_migrates_without_losing_translations(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._dashboard(Path(tmp))
            messages = catalog.extract_messages(source)
            pack = {"locale": "it", "dashboard_titles": {"overview": "Panoramica"},
                    "strings": {"Battery Level": "Livello batteria", "Car": "Auto", "Details": "Dettagli"},
                    "passthrough": ["Current battery state"]}
            updated, stats = catalog.synchronize_catalog(pack, messages)
            self.assertEqual(updated["schema"], 2)
            self.assertEqual(updated["messages"]["dashboard.overview.title"]["translation"], "Panoramica")
            self.assertEqual(updated["messages"]["dashboard.overview.panel[7].title"]["translation"], "Livello batteria")
            self.assertGreaterEqual(stats["translated"], 3)

    def test_source_change_marks_context_for_review_but_is_not_rendered_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            messages = catalog.extract_messages(self._dashboard(Path(tmp), panel_title="Battery"))
            pack = {"schema": 2, "locale": "it", "messages": {
                "dashboard.overview.panel[7].title": {
                    "source": "Battery Level", "translation": "Livello batteria", "status": "translated"}}}
            updated, stats = catalog.synchronize_catalog(pack, messages)
            entry = updated["messages"]["dashboard.overview.panel[7].title"]
            self.assertEqual(entry["source"], "Battery")
            self.assertEqual(entry["translation"], "Livello batteria")
            self.assertEqual(entry["status"], "needs_review")
            self.assertEqual(stats["needs_review"], 1)
            self.assertEqual(catalog.resolve_translation(updated, "dashboard.overview.panel[7].title", "Battery", "overview"), "Battery")

    def test_generator_is_language_agnostic_preserves_sql_and_clears_numeric_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._dashboard(root)
            output = root / "out"
            translations = root / "locales"
            translations.mkdir()
            pack_path = translations / "de.json"
            pack_path.write_text(json.dumps({
                "locale": "de", "dashboard_titles": {"overview": "Übersicht", "details": "Details"},
                "strings": {"Battery Level": "Batteriestand", "Car": "Auto", "Details": "Details"},
            }), encoding="utf-8")
            generate.generate_locale(source, pack_path, output)
            localized = json.loads((output / "de" / "overview.json").read_text())
            self.assertEqual(localized["title"], "Übersicht")
            self.assertEqual(localized["panels"][0]["title"], "Batteriestand")
            self.assertEqual(localized["panels"][0]["targets"][0]["rawSql"],
                             "SELECT level AS battery_level FROM positions WHERE car_id = $car_id")
            self.assertIsNone(localized["id"])
            self.assertEqual(localized["uid"], "overview-de")
            self.assertEqual(localized["links"][0]["url"], "/d/details-de/something")
            self.assertIn("TeslamateCustomDashboards-de", localized["tags"])

    def test_context_override_beats_legacy_source_translation(self):
        pack = {"schema": 2, "locale": "it", "strings": {"State": "Stato"}, "messages": {
            "dashboard.overview.panel[7].title": {"source": "State", "translation": "Condizione", "status": "translated"}}}
        self.assertEqual(catalog.resolve_translation(pack, "dashboard.overview.panel[7].title", "State", "overview"), "Condizione")

    def test_link_rewrite_matches_exact_uid_segment_not_prefix(self):
        result = generate.rewrite_links({"url": "/d/abc-def/view", "linkUrl": "/d/abc/view?x=1"},
                                        {"abc": "abc-it", "abc-def": "abc-def-it"})
        self.assertEqual(result["url"], "/d/abc-def-it/view")
        self.assertEqual(result["linkUrl"], "/d/abc-it/view?x=1")

    def test_placeholder_validation_rejects_lost_or_renamed_variables(self):
        with self.assertRaisesRegex(ValueError, "placeholder mismatch"):
            catalog.validate_pack({"locale": "fr", "strings": {"Cost ($currency) per $length_unit": "Coût par km"}})
        catalog.validate_pack({"locale": "fr", "strings": {"Cost ($currency) per $length_unit": "Coût ($currency) par $length_unit"}})

    def test_uid_is_deterministic_valid_and_max_40_chars(self):
        long_uid = "this-is-an-extremely-long-dashboard-uid-that-needs-shortening"
        first = generate.localized_uid(long_uid, "fr")
        self.assertEqual(first, generate.localized_uid(long_uid, "fr"))
        self.assertLessEqual(len(first), 40)
        self.assertTrue(first.endswith("-fr"))

    def test_generation_removes_stale_files_for_locale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._dashboard(root)
            translations = root / "locales"
            translations.mkdir()
            pack_path = translations / "es.json"
            pack_path.write_text(json.dumps({"locale": "es"}), encoding="utf-8")
            output = root / "out"
            stale = output / "es" / "stale.json"
            stale.parent.mkdir(parents=True)
            stale.write_text("{}")
            generate.generate_locale(source, pack_path, output)
            self.assertFalse(stale.exists())
            self.assertTrue((output / "es" / "overview.json").exists())

    def test_discover_pack_filename_must_match_locale(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "german.json"
            path.write_text(json.dumps({"locale": "de"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "filename must match locale"):
                catalog.discover_packs(Path(tmp))

    def test_manifest_allows_preview_locales_but_requires_complete_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            locales = root / "locales"
            locales.mkdir()
            for locale in ("it", "de", "fr", "es"):
                (locales / f"{locale}.json").write_text(json.dumps({"locale": locale}), encoding="utf-8")
            packs = catalog.discover_packs(locales)
            manifest_path = root / "locales.json"
            manifest_path.write_text(json.dumps({"default": "it", "locales": {
                "it": {"maturity": "complete"}, "de": {"maturity": "preview"},
                "fr": {"maturity": "preview"}, "es": {"maturity": "preview"}}}), encoding="utf-8")
            manifest = update_catalog.load_manifest(manifest_path)
            update_catalog.validate_manifest(manifest, packs)
            self.assertEqual(manifest["locales"]["it"]["maturity"], "complete")

    def test_generated_validator_accepts_safe_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._dashboard(root)
            translations = root / "locales"
            translations.mkdir()
            pack_path = translations / "fr.json"
            pack_path.write_text(json.dumps({"locale": "fr", "strings": {"Battery Level": "Niveau de batterie"}}), encoding="utf-8")
            output = root / "out"
            generate.generate_locale(source, pack_path, output)
            self.assertEqual(validate_generated.validate_locale(source, output, "fr"), [])


if __name__ == "__main__":
    unittest.main()
