#!/usr/bin/env python3
"""Generate localized Grafana dashboards from canonical English sources."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from catalog import (
    LOCALIZABLE_KEYS,
    discover_packs,
    list_segment,
    load_json,
    resolve_translation,
    token,
    validate_pack,
)

TECHNICAL_KEYS = {"rawSql", "query", "definition", "expression"}
UID_LIMIT = 40
CUSTOM_TAG = "TeslamateCustomDashboards"
DASHBOARD_URL_RE = re.compile(r"(?P<prefix>/d/)(?P<uid>[^/?#]+)")


def localized_uid(uid: str, locale: str) -> str:
    suffix = f"-{locale}"
    candidate = f"{uid}{suffix}"
    if len(candidate) <= UID_LIMIT:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:8]
    keep = UID_LIMIT - len(suffix) - len(digest) - 1
    return f"{uid[:max(1, keep)]}-{digest}{suffix}"


def build_uid_map(paths: list[Path], locale: str) -> dict[str, str]:
    result: dict[str, str] = {}
    generated: dict[str, str] = {}
    for path in paths:
        data = load_json(path)
        uid = data.get("uid")
        if not isinstance(uid, str) or not uid:
            continue
        new_uid = localized_uid(uid, locale)
        previous = generated.get(new_uid)
        if previous and previous != uid:
            raise ValueError(f"localized UID collision: {previous!r} and {uid!r} -> {new_uid!r}")
        generated[new_uid] = uid
        result[uid] = new_uid
    return result


def rewrite_links(value, uid_map: dict[str, str], key: str = ""):
    if key in TECHNICAL_KEYS:
        return copy.deepcopy(value)
    if isinstance(value, dict):
        return {k: rewrite_links(v, uid_map, k) for k, v in value.items()}
    if isinstance(value, list):
        return [rewrite_links(v, uid_map, key) for v in value]
    if isinstance(value, str) and key in {"url", "linkUrl"}:
        def replace(match: re.Match[str]) -> str:
            uid = match.group("uid")
            return match.group("prefix") + uid_map.get(uid, uid)
        return DASHBOARD_URL_RE.sub(replace, value)
    return value


def rewrite_tags(value, locale: str) -> None:
    if not isinstance(value, dict):
        return
    tags = value.get("tags")
    if isinstance(tags, list):
        value["tags"] = [f"{CUSTOM_TAG}-{locale}" if tag == CUSTOM_TAG else tag for tag in tags]
    for child in value.values():
        if isinstance(child, dict):
            rewrite_tags(child, locale)
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    rewrite_tags(item, locale)


def localize_value(value, context: str, dashboard: str, pack: dict):
    if isinstance(value, list):
        return [localize_value(item, f"{context}[{index}]", dashboard, pack) for index, item in enumerate(value)]
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
            result[key] = {
                source_name: resolve_translation(
                    pack,
                    f"{context}.renameByName[{token(source_name)}]",
                    target,
                    dashboard,
                ) if isinstance(target, str) and target.strip() else copy.deepcopy(target)
                for source_name, target in item.items()
            }
            continue
        if key == "value" and value.get("id") == "displayName" and isinstance(item, str) and item.strip():
            result[key] = resolve_translation(pack, f"{context}.value", item, dashboard)
            continue
        if isinstance(item, list):
            result[key] = [
                localize_value(child, f"{context}.{list_segment(key, child, index)}", dashboard, pack)
                for index, child in enumerate(item)
            ]
        elif isinstance(item, dict):
            result[key] = localize_value(item, f"{context}.{key}", dashboard, pack)
        else:
            result[key] = copy.deepcopy(item)
    return result


def localize_dashboard(source: dict, dashboard: str, pack: dict, uid_map: dict[str, str]) -> dict:
    locale = validate_pack(pack)
    result = localize_value(copy.deepcopy(source), f"dashboard.{dashboard}", dashboard, pack)
    result = rewrite_links(result, uid_map)
    uid = source.get("uid")
    if isinstance(uid, str) and uid in uid_map:
        result["uid"] = uid_map[uid]
    result["id"] = None
    rewrite_tags(result, locale)
    return result


def generate_locale(source_dir: Path, pack_path: Path, output_root: Path) -> int:
    pack = load_json(pack_path)
    locale = validate_pack(pack, pack_path)
    paths = sorted(source_dir.rglob("*.json"))
    if not paths:
        raise ValueError(f"no dashboard JSON files found in {source_dir}")
    uid_map = build_uid_map(paths, locale)
    out_dir = output_root / locale
    if out_dir.exists():
        shutil.rmtree(out_dir)
    count = 0
    for path in paths:
        dashboard = path.relative_to(source_dir).with_suffix("").as_posix()
        localized = localize_dashboard(load_json(path), dashboard, pack, uid_map)
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

    requested = set(args.locale or [])
    packs = [(path, pack) for path, pack in discover_packs(Path(args.translations))
             if not requested or pack["locale"] in requested]
    if not packs:
        parser.error(f"no matching locale packs found in {args.translations}")
    found = {pack["locale"] for _, pack in packs}
    missing_requested = requested - found
    if missing_requested:
        parser.error("unknown locale(s): " + ", ".join(sorted(missing_requested)))

    total = 0
    for pack_path, pack in packs:
        count = generate_locale(Path(args.source), pack_path, Path(args.output))
        print(f"{pack['locale']}: generated {count} dashboards in {Path(args.output) / pack['locale']}")
        total += count
    print(f"generated {total} localized dashboards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
