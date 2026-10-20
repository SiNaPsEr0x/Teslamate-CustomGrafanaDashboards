#!/usr/bin/env python3
"""Validate generated localized dashboards against their canonical sources."""
from __future__ import annotations

import argparse
from pathlib import Path
import re

from catalog import discover_packs, load_json
from generate import CUSTOM_TAG, build_uid_map

TECHNICAL_KEYS = {"rawSql", "query", "definition", "expression", "datasource"}
DASHBOARD_URL_RE = re.compile(r"(?P<prefix>/d/)(?P<uid>[^/?#]+)")


def collect_technical(value, path="$"):
    result = []
    if isinstance(value, dict):
        for key, item in value.items():
            here = f"{path}.{key}"
            if key in TECHNICAL_KEYS:
                result.append((here, item))
            else:
                result.extend(collect_technical(item, here))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.extend(collect_technical(item, f"{path}[{index}]"))
    return result


def dashboard_urls(value):
    result = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"url", "linkUrl"} and isinstance(item, str):
                result.append(item)
            else:
                result.extend(dashboard_urls(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(dashboard_urls(item))
    return result


def validate_locale(source_dir: Path, output_root: Path, locale: str) -> list[str]:
    errors: list[str] = []
    source_paths = sorted(source_dir.rglob("*.json"))
    generated_dir = output_root / locale
    generated_paths = sorted(generated_dir.rglob("*.json")) if generated_dir.exists() else []
    expected_rel = [p.relative_to(source_dir) for p in source_paths]
    actual_rel = [p.relative_to(generated_dir) for p in generated_paths]
    if expected_rel != actual_rel:
        missing = sorted(set(expected_rel) - set(actual_rel))
        extra = sorted(set(actual_rel) - set(expected_rel))
        if missing:
            errors.append(f"{locale}: missing generated files: {', '.join(map(str, missing))}")
        if extra:
            errors.append(f"{locale}: unexpected generated files: {', '.join(map(str, extra))}")
        return errors

    uid_map = build_uid_map(source_paths, locale)
    seen_uids: set[str] = set()
    for source_path, rel in zip(source_paths, expected_rel):
        generated_path = generated_dir / rel
        source = load_json(source_path)
        generated = load_json(generated_path)
        label = f"{locale}/{rel.as_posix()}"

        if generated.get("id") is not None:
            errors.append(f"{label}: top-level dashboard id must be null")

        source_uid = source.get("uid")
        generated_uid = generated.get("uid")
        if isinstance(source_uid, str) and source_uid:
            expected_uid = uid_map[source_uid]
            if generated_uid != expected_uid:
                errors.append(f"{label}: uid {generated_uid!r} != expected {expected_uid!r}")
        if isinstance(generated_uid, str):
            if len(generated_uid) > 40:
                errors.append(f"{label}: uid exceeds 40 characters")
            if generated_uid in seen_uids:
                errors.append(f"{label}: duplicate generated uid {generated_uid!r}")
            seen_uids.add(generated_uid)

        if collect_technical(source) != collect_technical(generated):
            errors.append(f"{label}: SQL/query/datasource technical fields changed")

        source_tags = source.get("tags") or []
        generated_tags = generated.get("tags") or []
        if CUSTOM_TAG in source_tags and f"{CUSTOM_TAG}-{locale}" not in generated_tags:
            errors.append(f"{label}: localized dashboard tag missing")

        generated_urls = dashboard_urls(generated)
        for url in dashboard_urls(source):
            match = DASHBOARD_URL_RE.search(url)
            if not match or match.group("uid") not in uid_map:
                continue
            expected = DASHBOARD_URL_RE.sub(
                lambda m: m.group("prefix") + uid_map.get(m.group("uid"), m.group("uid")),
                url,
            )
            if expected not in generated_urls:
                errors.append(f"{label}: localized dashboard link missing for {url!r}")

    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="dashboards")
    parser.add_argument("--translations", default="i18n/locales")
    parser.add_argument("--output", required=True)
    parser.add_argument("--locale", action="append")
    args = parser.parse_args(argv)

    requested = set(args.locale or [])
    packs = discover_packs(Path(args.translations))
    locales = [pack["locale"] for _, pack in packs if not requested or pack["locale"] in requested]
    unknown = requested - set(locales)
    if unknown:
        parser.error("unknown locale(s): " + ", ".join(sorted(unknown)))

    errors = []
    for locale in locales:
        locale_errors = validate_locale(Path(args.source), Path(args.output), locale)
        if locale_errors:
            errors.extend(locale_errors)
        else:
            print(f"{locale}: generated dashboards valid")
    for error in errors:
        print("ERROR", error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
