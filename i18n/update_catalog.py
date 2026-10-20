#!/usr/bin/env python3
"""Synchronize contextual translation metadata for every locale pack."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from catalog import extract_messages, load_json, synchronize_catalog


def _same_catalog(pack: dict, synchronized: dict) -> bool:
    return (
        pack.get("schema") == 2
        and pack.get("messages") == synchronized.get("messages")
        and pack.get("obsolete_messages") == synchronized.get("obsolete_messages")
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="dashboards")
    parser.add_argument("--translations", default="i18n/locales")
    parser.add_argument("--locale", action="append")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail when messages are missing or need review",
    )
    parser.add_argument(
        "--allow-legacy",
        action="store_true",
        help="accept a legacy pack during migration if coverage is complete",
    )
    args = parser.parse_args(argv)

    messages = extract_messages(Path(args.source))
    translations = Path(args.translations)
    requested = set(args.locale or [])
    packs = []
    for path in sorted(translations.glob("*.json")):
        pack = load_json(path)
        if requested and pack.get("locale") not in requested:
            continue
        packs.append((path, pack))
    if not packs:
        parser.error(f"no locale packs found in {translations}")

    failed = False
    for path, pack in packs:
        synchronized, stats = synchronize_catalog(pack, messages)
        schema_synced = _same_catalog(pack, synchronized)
        if args.write:
            path.write_text(
                json.dumps(synchronized, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        elif not schema_synced and not (args.allow_legacy and pack.get("schema") != 2):
            failed = True

        if args.strict and (stats["missing"] or stats["needs_review"]):
            failed = True

        print(
            f"{pack['locale']}: messages={len(messages)} "
            f"translated={stats['translated']} passthrough={stats['passthrough']} "
            f"missing={stats['missing']} review={stats['needs_review']} "
            f"obsolete={stats['obsolete']} "
            f"schema={'v2' if schema_synced else 'migration-needed'}"
        )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
