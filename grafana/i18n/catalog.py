#!/usr/bin/env python3
"""Context-aware translation catalog support for Grafana dashboards.

Schema v2 is deliberately backward compatible with the existing TeslaMate
translation packs. Existing ``strings`` and ``dashboard_titles`` sections are
used to seed contextual ``messages`` and can remain in the pack while the
runtime localizer is migrated.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterator

LOCALIZABLE_KEYS = {
    "title",
    "description",
    "label",
    "displayName",
    "legendFormat",
    "tooltip",
    "noValue",
    "text",
    "alias",
}
TECHNICAL_STRING_KEYS = {"rawSql", "query", "definition"}
_STATUS_VALUES = {"translated", "missing", "needs_review", "passthrough"}
_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.:@/-]+")


@dataclass(frozen=True)
class Message:
    key: str
    source: str
    dashboard: str


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def _token(value: object) -> str:
    text = str(value).strip()
    text = _SAFE_TOKEN_RE.sub("_", text).strip("_")
    return text or "unknown"


def _list_segment(container_key: str, item: object, index: int) -> str:
    if isinstance(item, dict):
        if container_key == "panels" and item.get("id") is not None:
            return f"panel[{_token(item['id'])}]"
        if container_key == "list" and item.get("name"):
            return f"variable[{_token(item['name'])}]"
        for discriminator in ("refId", "uid", "name", "id"):
            if item.get(discriminator) not in (None, ""):
                return f"{container_key}[{discriminator}={_token(item[discriminator])}]"
    return f"{container_key}[{index}]"


def _iter_value(value: object, context: str, dashboard: str) -> Iterator[Message]:
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_value(item, f"{context}[{index}]", dashboard)
        return
    if not isinstance(value, dict):
        return

    for key, item in value.items():
        if key in TECHNICAL_STRING_KEYS and isinstance(item, str):
            continue

        if key in LOCALIZABLE_KEYS and isinstance(item, str) and item.strip():
            yield Message(f"{context}.{key}", item, dashboard)
            continue

        if key == "renameByName" and isinstance(item, dict):
            for source_name, target in item.items():
                if isinstance(target, str) and target.strip():
                    yield Message(
                        f"{context}.renameByName[{_token(source_name)}]",
                        target,
                        dashboard,
                    )
            continue

        if key == "value" and value.get("id") == "displayName" and isinstance(item, str) and item.strip():
            yield Message(f"{context}.value", item, dashboard)
            continue

        if isinstance(item, list):
            for index, child in enumerate(item):
                segment = _list_segment(key, child, index)
                yield from _iter_value(child, f"{context}.{segment}", dashboard)
        elif isinstance(item, dict):
            yield from _iter_value(item, f"{context}.{key}", dashboard)


def extract_messages(source_dir: Path) -> dict[str, Message]:
    """Extract deterministic, contextual message keys from dashboard JSON files."""
    source_dir = Path(source_dir)
    paths = sorted(source_dir.rglob("*.json"))
    if not paths:
        raise ValueError(f"no dashboard JSON files found in {source_dir}")

    result: dict[str, Message] = {}
    for path in paths:
        dashboard_key = path.relative_to(source_dir).with_suffix("").as_posix()
        data = load_json(path)
        prefix = f"dashboard.{dashboard_key}"
        for message in _iter_value(data, prefix, dashboard_key):
            previous = result.get(message.key)
            if previous and previous.source != message.source:
                raise ValueError(
                    f"context key collision for {message.key!r}: "
                    f"{previous.source!r} != {message.source!r}"
                )
            result[message.key] = message
    return dict(sorted(result.items()))


def _seed_translation(message: Message, pack: dict) -> tuple[str, str]:
    passthrough = set(pack.get("passthrough") or [])
    if message.source in passthrough:
        return message.source, "passthrough"

    legacy_titles = pack.get("dashboard_titles") or {}
    if message.key == f"dashboard.{message.dashboard}.title":
        translated = legacy_titles.get(message.dashboard)
        if isinstance(translated, str) and translated:
            return translated, "translated"

    legacy_strings = pack.get("strings") or {}
    translated = legacy_strings.get(message.source)
    if isinstance(translated, str) and translated:
        return translated, "translated"
    return "", "missing"


def synchronize_catalog(pack: dict, messages: dict[str, Message]) -> tuple[dict, dict[str, int]]:
    """Return a schema-v2 catalog plus synchronization statistics.

    Existing contextual translations are preserved. If upstream changes the
    English source for an existing context, the translation is retained but
    marked ``needs_review`` rather than silently trusted.
    """
    if not isinstance(pack.get("locale"), str) or not pack["locale"].strip():
        raise ValueError("translation pack must contain a non-empty 'locale'")

    current = pack.get("messages") or {}
    if not isinstance(current, dict):
        raise ValueError("'messages' must be an object when present")

    synchronized: dict[str, dict[str, str]] = {}
    stats = {"translated": 0, "missing": 0, "needs_review": 0, "passthrough": 0, "obsolete": 0}

    for key, message in messages.items():
        old = current.get(key)
        if isinstance(old, dict):
            translation = old.get("translation", "")
            if not isinstance(translation, str):
                translation = ""
            old_source = old.get("source")
            if old_source == message.source:
                status = old.get("status")
                if status not in _STATUS_VALUES:
                    status = "translated" if translation else "missing"
            else:
                status = "needs_review" if translation else "missing"
        else:
            translation, status = _seed_translation(message, pack)

        synchronized[key] = {
            "source": message.source,
            "translation": translation,
            "status": status,
        }
        stats[status] += 1

    obsolete: dict[str, dict] = {}
    previous_obsolete = pack.get("obsolete_messages") or {}
    if isinstance(previous_obsolete, dict):
        obsolete.update(previous_obsolete)
    for key, entry in current.items():
        if key not in messages and isinstance(entry, dict):
            obsolete[key] = entry
    for key in list(obsolete):
        if key in messages:
            del obsolete[key]
    stats["obsolete"] = len(obsolete)

    result = dict(pack)
    result["schema"] = 2
    result["messages"] = synchronized
    if obsolete:
        result["obsolete_messages"] = dict(sorted(obsolete.items()))
    else:
        result.pop("obsolete_messages", None)
    return result, stats


def catalog_is_synchronized(pack: dict, synchronized: dict) -> bool:
    return (
        pack.get("schema") == 2
        and pack.get("messages") == synchronized.get("messages")
        and pack.get("obsolete_messages") == synchronized.get("obsolete_messages")
    )
