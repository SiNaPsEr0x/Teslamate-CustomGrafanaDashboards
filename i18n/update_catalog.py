#!/usr/bin/env python3
"""Synchronize contextual translation metadata for all locale packs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from catalog import discover_packs, extract_messages, synchronize_catalog

MATURITY_VALUES = {"complete", "preview"}


def load_manifest(path: Path | None) -> dict:
    if path is None:
        return {"locales": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("locales"), dict):
        raise ValueError(f"{path}: expected object with a 'locales' object")
    for locale, meta in data["locales"].items():
        if not isinstance(meta, dict) or meta.get("maturity") not in MATURITY_VALUES:
            raise ValueError(f"{path}: locale {locale!r} needs maturity complete|preview")
    return data


def validate_manifest(manifest: dict, packs: list[tuple[Path, dict]]) -> None:
    pack_locales = {pack["locale"] for _, pack in packs}
    manifest_locales = set(manifest.get("locales", {}))
    missing_files = manifest_locales - pack_locales
    unlisted = pack_locales - manifest_locales
    if missing_files:
        raise ValueError("manifest locale(s) without pack: " + ", ".join(sorted(missing_files)))
    if manifest_locales and unlisted:
        raise ValueError("locale pack(s) missing from manifest: " + ", ".join(sorted(unlisted)))
    default = manifest.get("default")
    if default is not None and default not in pack_locales:
        raise ValueError(f"manifest default locale {default!r} has no pack")


def same_catalog(pack: dict, synchronized: dict) -> bool:
    return (
        pack.get("schema") == 2
        and pack.get("messages") == synchronized.get("messages")
        and pack.get("obsolete_messages") == synchronized.get("obsolete_messages")
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="dashboards")
    parser.add_argument("--translations", default="i18n/locales")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--locale", action="append")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--strict", action="store_true", help="require 100% coverage for every selected locale")
    parser.add_argument("--enforce-maturity", action="store_true", help="require 100% coverage only for manifest locales marked complete")
    parser.add_argument("--allow-legacy", action="store_true", help="accept non-schema-v2 packs during migration")
    args = parser.parse_args(argv)

    messages = extract_messages(Path(args.source))
    all_packs = discover_packs(Path(args.translations))
    manifest = load_manifest(args.manifest)
    if args.manifest:
        validate_manifest(manifest, all_packs)

    requested = set(args.locale or [])
    packs = [(path, pack) for path, pack in all_packs if not requested or pack["locale"] in requested]
    if not packs:
        parser.error(f"no matching locale packs found in {args.translations}")
    missing_requested = requested - {pack["locale"] for _, pack in packs}
    if missing_requested:
        parser.error("unknown locale(s): " + ", ".join(sorted(missing_requested)))

    failed = False
    for path, pack in packs:
        synchronized, stats = synchronize_catalog(pack, messages)
        schema_synced = same_catalog(pack, synchronized)
        if args.write:
            path.write_text(json.dumps(synchronized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        elif not schema_synced and not (args.allow_legacy and pack.get("schema") != 2):
            failed = True

        maturity = (manifest.get("locales", {}).get(pack["locale"], {}) or {}).get("maturity", "preview")
        requires_complete = args.strict or (args.enforce_maturity and maturity == "complete")
        if requires_complete and (stats["missing"] or stats["needs_review"]):
            failed = True

        covered = stats["translated"] + stats["passthrough"]
        coverage = 100.0 * covered / max(1, len(messages))
        state = "updated" if args.write and not schema_synced else "ok" if schema_synced else "legacy"
        print(
            f"{pack['locale']}: {state}; maturity={maturity}; messages={len(messages)}; "
            f"coverage={coverage:.1f}%; translated={stats['translated']}; "
            f"passthrough={stats['passthrough']}; missing={stats['missing']}; "
            f"review={stats['needs_review']}; obsolete={stats['obsolete']}"
        )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
