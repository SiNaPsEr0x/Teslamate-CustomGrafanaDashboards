#!/usr/bin/env python3
"""Extract Grafana UI strings and synchronize all locale catalogs in a directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from catalog import catalog_is_synchronized, extract_messages, load_json, synchronize_catalog


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="source dashboard directory")
    parser.add_argument("--translations", required=True, help="directory containing locale JSON packs")
    parser.add_argument("--locale", action="append", help="only process this locale; may be repeated")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write synchronized catalogs")
    mode.add_argument("--check", action="store_true", help="fail if catalogs are not synchronized")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also fail if any message is missing or needs review",
    )
    args = parser.parse_args(argv)

    source = Path(args.source)
    translations = Path(args.translations)
    messages = extract_messages(source)
    requested = set(args.locale or [])
    packs = []
    for path in sorted(translations.glob("*.json")):
        pack = load_json(path)
        locale = pack.get("locale")
        if requested and locale not in requested:
            continue
        packs.append((path, pack))

    if not packs:
        parser.error(f"no locale JSON packs found in {translations}")

    failed = False
    for path, pack in packs:
        synchronized, stats = synchronize_catalog(pack, messages)
        locale = pack["locale"]
        changed = not catalog_is_synchronized(pack, synchronized)
        if args.write:
            path.write_text(
                json.dumps(synchronized, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        elif changed:
            failed = True

        if args.strict and (stats["missing"] or stats["needs_review"]):
            failed = True

        state = "updated" if args.write and changed else "ok" if not changed else "out-of-sync"
        print(
            f"{locale}: {state}; messages={len(messages)} "
            f"translated={stats['translated']} passthrough={stats['passthrough']} "
            f"missing={stats['missing']} review={stats['needs_review']} "
            f"obsolete={stats['obsolete']}"
        )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
