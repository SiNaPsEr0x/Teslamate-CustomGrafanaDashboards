#!/bin/bash
set -euo pipefail

REPO_URL="${TESLAMATE_CUSTOM_REPO:-https://github.com/SiNaPsEr0x/Teslamate-CustomGrafanaDashboards.git}"
TARGET="${TESLAMATE_CUSTOM_DIR:-$HOME/Teslamate-CustomGrafanaDashboards}"
LOCALE="${TESLAMATE_CUSTOM_LOCALE:-it}"

sudo apt update
sudo apt install -y git python3

if [ -d "$TARGET/.git" ]; then
  git -C "$TARGET" pull --ff-only
else
  git clone "$REPO_URL" "$TARGET"
fi

TESLAMATE_CUSTOM_LOCALE="$LOCALE" "$TARGET/scripts/localize.sh"
