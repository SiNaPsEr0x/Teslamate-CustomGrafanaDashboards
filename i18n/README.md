# Grafana localization

This directory contains the language-agnostic localization layer for the custom
TeslaMate Grafana dashboards.

## Design

- `../dashboards/` is the only canonical dashboard source and remains English.
- `locales/<locale>.json` contains a language pack.
- `catalog.py` extracts stable contextual message keys from dashboard JSON.
- `update_catalog.py` updates language packs when upstream text changes.
- `generate.py` creates localized dashboard copies without modifying SQL,
  Grafana queries, datasource identifiers or the English source files.
- Localized dashboards get locale-specific UIDs and the
  `TeslamateCustomDashboards-<locale>` tag so multiple languages can coexist.

A locale pack can initially use the compact legacy sections `strings`,
`dashboard_titles` and `passthrough`. Running `update_catalog.py --write`
migrates it to schema v2 and adds contextual `messages`. Contextual entries take
precedence over source-string translations, so the same English text can be
translated differently in different panels.

## Add a language

1. Copy an existing file under `locales/` and change `locale`.
2. Add translations in `strings`/`dashboard_titles`, or run the catalog updater
   and fill the generated `messages`.
3. Validate coverage.
4. Generate the localized dashboards.

```bash
python3 i18n/update_catalog.py \
  --source dashboards \
  --translations i18n/locales \
  --locale it \
  --write

python3 i18n/update_catalog.py \
  --source dashboards \
  --translations i18n/locales \
  --check \
  --strict

python3 i18n/generate.py \
  --source dashboards \
  --translations i18n/locales \
  --output .localized
```

To generate only one language, repeat `--locale <code>` as needed.

## Upstream updates

After dashboard changes, `--check --strict` detects new untranslated strings and
schema-v2 entries whose English source changed. Existing translations are kept
and marked `needs_review`; removed contexts are retained under
`obsolete_messages`, so translator work is never silently discarded.

The single repository validation workflow runs dashboard validation, unit tests
for the localization engine, and translation coverage checks.
