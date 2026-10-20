#!/bin/bash
set -euo pipefail

REPO_URL="${TESLAMATE_CUSTOM_REPO:-https://github.com/SiNaPsEr0x/Teslamate-CustomGrafanaDashboards.git}"
TARGET="${TESLAMATE_CUSTOM_DIR:-$HOME/Teslamate-CustomGrafanaDashboards}"
LOCALE="${TESLAMATE_CUSTOM_LOCALE:-it}"

missing=()
command -v git >/dev/null 2>&1 || missing+=(git)
command -v python3 >/dev/null 2>&1 || missing+=(python3)
if ((${#missing[@]})); then
  sudo apt update
  sudo apt install -y "${missing[@]}"
fi

if [ -d "$TARGET/.git" ]; then
  git -C "$TARGET" remote set-url origin "$REPO_URL"
  git -C "$TARGET" fetch --prune origin main
  git -C "$TARGET" checkout main
  git -C "$TARGET" merge --ff-only origin/main
else
  git clone --branch main --single-branch "$REPO_URL" "$TARGET"
fi

TESLAMATE_CUSTOM_LOCALE="$LOCALE" "$TARGET/scripts/localize.sh"
