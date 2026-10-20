#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
LOCALE="${TESLAMATE_CUSTOM_LOCALE:-it}"
OUTPUT="${TESLAMATE_CUSTOM_OUTPUT:-$ROOT/.localized}"

python3 "$ROOT/i18n/generate.py" \
  --source "$ROOT/dashboards" \
  --translations "$ROOT/i18n/locales" \
  --locale "$LOCALE" \
  --output "$OUTPUT"

python3 "$ROOT/i18n/validate_generated.py" \
  --source "$ROOT/dashboards" \
  --translations "$ROOT/i18n/locales" \
  --locale "$LOCALE" \
  --output "$OUTPUT"

printf 'Localized dashboards ready: %s\n' "$OUTPUT/$LOCALE"
