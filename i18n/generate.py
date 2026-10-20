#!/usr/bin/env python3
"""Generate localized Grafana dashboards from one canonical English source tree."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from catalog import LOCALIZABLE_KEYS, load_json, resolve_translation, validate_locale

TECHNICAL_KEYS = {"rawSql", "query", "definition", "expression"}
UID_LIMIT = 40
CUSTOM_TAG = "TeslamateCustomDashboards"


def localized_uid(uid: str, locale: str) -> str:
    suffix = f"-{locale}"
    candidate = f"{uid}{suffix}"
    if len(candidate) <= UID_LIMIT:
        return candidate
    digest = hashlib.sha1(candidate.encode("utf-8")).hexdigest()[:8]
    keep = UID_LIMIT - len(suffix) - len(digest) - 1
    return f"{uid[:max(1, keep)]}-{digest}{suffix}"


def build_uid_map(paths: list[Path], locale: str) -> dict[str, str]:
    result = {}
    for path in paths:
        data = load_json(path)
        uid = data.get("uid")
        if isinstance(uid, str) and uid:
            result[uid] = localized_uid(uid, locale)
    return result


def rewrite_links(value, uid_map: dict[str, str], key: str = ""):
    if key in TECHNICAL_KEYS:
        return copy.deepcopy(value)
    if isinstance(value, dict):
        return {k: rewrite_links(v, uid_map, k) for k, v in value.items()}
    if isinstance(value, list):
        return [rewrite_links(v, uid_map, key) for v in value]
    if isinstance(value, str) and key in {"url", "linkUrl"}:
        for before, after in uid_map.items():
            value = value.replace(f"/d/{before}", f"/d/{after}")
    return value


def rewrite_tags(value, locale: str):
    if not isinstance(value, dict):
        return
    tags = value.get("tags")
    if isinstance(tags, list):
        value["tags"] = [
            f"{CUSTOM_TAG}-{locale}" if tag == CUSTOM_TAG else tag
            for tag in tags
        ]
    for child in value.values():
        if isinstance(child, dict):
            rewrite_tags(child, locale)
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    rewrite_tags(item, locale)


def localize_value(value, context: str, dashboard: str, pack: dict):
    from catalog import list_segment, token

    if isinstance(value, list):
        return [
            localize_value(item, f"{context}[{index}]", dashboard, pack)
            for index, item in enumerate(value)
        ]
    if not isinstance(value, dict):
        return copy.deepcopy(value)

    result = {}
    for key, item in value.items():
        if key in TECHNICAL_KEYS and isinstance(item, str):
            result[key] = item
            continue

        if key in LOCALIZABLE_KEYS and isinstance(item, str) and item.strip():
            result[key] = resolve_translation(pack, f"{context}.{key}", item, dashboard)
            continue

        if key == "renameByName" and isinstance(item, dict):
            translated = {}
            for source_name, target in item.items():
                if isinstance(target, str) and target.strip():
                    translated[source_name] = resolve_translation(
                        pack,
                        f"{context}.renameByName[{token(source_name)}]",
                        target,
                        dashboard,
                    )
                else:
                    translated[source_name] = copy.deepcopy(target)
            result[key] = translated
            continue

        if key == "value" and value.get("id") == "displayName" and isinstance(item, str) and item.strip():
            result[key] = resolve_translation(pack, f"{context}.value", item, dashboard)
            continue

        if isinstance(item, list):
            children = []
            for index, child in enumerate(item):
                segment = list_segment(key, child, index)
                children.append(localize_value(child, f"{context}.{segment}", dashboard, pack))
            result[key] = children
        elif isinstance(item, dict):
            result[key] = localize_value(item, f"{context}.{key}", dashboard, pack)
        else:
            result[key] = copy.deepcopy(item)
    return result


def localize_dashboard(source: dict, dashboard: str, pack: dict, uid_map: dict[str, str]) -> dict:
    locale = validate_locale(pack.get("locale"))
    result = localize_value(copy.deepcopy(source), f"dashboard.{dashboard}", dashboard, pack)
    result = rewrite_links(result, uid_map)
    uid = source.get("uid")
    if isinstance(uid, str) and uid in uid_map:
        result["uid"] = uid_map[uid]
    rewrite_tags(result, locale)
    return result


def generate_locale(source_dir: Path, pack_path: Path, output_root: Path) -> int:
    pack = load_json(pack_path)
    locale = validate_locale(pack.get("locale"))
    paths = sorted(source_dir.rglob("*.json"))
    if not paths:
        raise ValueError(f"no dashboard JSON files found in {source_dir}")
    uid_map = build_uid_map(paths, locale)
    out_dir = output_root / locale
    count = 0
    for path in paths:
        dashboard = path.relative_to(source_dir).with_suffix("").as_posix()
        source = load_json(path)
        localized = localize_dashboard(source, dashboard, pack, uid_map)
        target = out_dir / path.relative_to(source_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(localized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        count += 1
    return count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="dashboards")
    parser.add_argument("--translations", default="i18n/locales")
    parser.add_argument("--output", required=True)
    parser.add_argument("--locale", action="append", help="only generate this locale; may be repeated")
    args = parser.parse_args(argv)

    source_dir = Path(args.source)
    translations = Path(args.translations)
    output_root = Path(args.output)
    requested = set(args.locale or [])
    packs = []
    for path in sorted(translations.glob("*.json")):
        pack = load_json(path)
        locale = validate_locale(pack.get("locale"))
        if requested and locale not in requested:
            continue
        packs.append(path)

    if not packs:
        parser.error(f"no locale packs found in {translations}")

    total = 0
    for pack_path in packs:
        count = generate_locale(source_dir, pack_path, output_root)
        locale = load_json(pack_path)["locale"]
        print(f"{locale}: generated {count} dashboards in {output_root / locale}")
        total += count
    print(f"generated {total} localized dashboards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
