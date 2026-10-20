# Grafana localization

This directory contains the language-agnostic localization layer for the custom
TeslaMate Grafana dashboards.

## Design

- `../dashboards/` is the only canonical source and remains English.
- `locales/<locale>.json` contains a language pack.
- `locales.json` declares the default language and maturity of each locale.
- `catalog.py` extracts stable contextual message keys from dashboard JSON.
- `update_catalog.py` detects new, changed and obsolete source strings.
- `generate.py` creates localized copies without changing SQL, queries,
  datasource identifiers or the canonical dashboard files.
- `validate_generated.py` compares generated files with the canonical sources
  and rejects technical-field changes, bad UIDs, stale files and broken links.
- Localized dashboards get locale-specific UIDs and the
  `TeslamateCustomDashboards-<locale>` tag.

## Included locales

| Locale | Language | Maturity |
| --- | --- | --- |
| `it` | Italiano | complete |
| `de` | Deutsch | preview |
| `fr` | Français | preview |
| `es` | Español | preview |

`complete` locales are required to cover every extractable message in CI.
`preview` locales are usable now but untranslated strings intentionally fall
back to the canonical English text while the catalog grows.

## Use a locale

Italian is the default:

```bash
./scripts/localize.sh
```

Select another installed locale:

```bash
TESLAMATE_CUSTOM_LOCALE=de ./scripts/localize.sh
TESLAMATE_CUSTOM_LOCALE=fr ./scripts/localize.sh
TESLAMATE_CUSTOM_LOCALE=es ./scripts/localize.sh
```

Generated files are written below `.localized/<locale>/` and are never committed.
The provided Compose sample mounts that generated directory into Grafana.

## Add a language

1. Add `locales/<code>.json` with a matching `locale` field.
2. Add the locale to `locales.json` as `preview`.
3. Translate dashboard titles and as many source strings as desired.
4. Preserve every Grafana/TeslaMate placeholder exactly (`$car_id`,
   `$length_unit`, `${preferred_range}`, and so on). The validator rejects a
   translation that drops or renames one.
5. When coverage reaches 100%, change its maturity to `complete`.

The code generator itself does not need to change for a new language.

## Update after upstream dashboard changes

```bash
python3 i18n/update_catalog.py \
  --source dashboards \
  --translations i18n/locales \
  --manifest i18n/locales.json \
  --check \
  --enforce-maturity \
  --allow-legacy
```

When an English source string changes, an existing contextual translation is
kept for translator reference and marked `needs_review`, but it is **not shown to
users** until reviewed. Runtime falls back to the new English source instead.
If a placeholder changed, the stale translation is discarded as unsafe and
reported missing.

## Generate and verify every language

```bash
rm -rf .localized-ci
python3 i18n/generate.py \
  --source dashboards \
  --translations i18n/locales \
  --output .localized-ci

python3 i18n/validate_generated.py \
  --source dashboards \
  --translations i18n/locales \
  --output .localized-ci
```

The repository's single validation workflow performs these checks automatically
when GitHub Actions is enabled for the fork.
