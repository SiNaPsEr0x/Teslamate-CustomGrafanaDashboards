#!/usr/bin/env python3
"""Context-aware translation catalog support for Grafana dashboards."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterator

LOCALIZABLE_KEYS = {
    "title", "description", "label", "displayName", "legendFormat",
    "tooltip", "noValue", "text", "alias",
}
TECHNICAL_STRING_KEYS = {
    "rawSql", "query", "definition", "expression", "datasource", "uid",
}
STATUS_VALUES = {"translated", "missing", "needs_review", "passthrough"}
SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.:@/-]+")
LOCALE_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
PLACEHOLDER_RE = re.compile(r"\$\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class Message:
    key: str
    source: str
    dashboard: str


def load_json(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def validate_locale(locale: str) -> str:
    if not isinstance(locale, str) or not LOCALE_RE.fullmatch(locale):
        raise ValueError(f"invalid locale code: {locale!r}")
    return locale


def placeholder_tokens(text: str) -> Counter[str]:
    return Counter(PLACEHOLDER_RE.findall(text))


def validate_placeholders(source: str, translation: str, where: str = "translation") -> None:
    expected = placeholder_tokens(source)
    actual = placeholder_tokens(translation)
    if expected != actual:
        missing = list((expected - actual).elements())
        extra = list((actual - expected).elements())
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("extra " + ", ".join(extra))
        raise ValueError(f"{where}: placeholder mismatch ({'; '.join(detail)})")


def validate_pack(pack: dict, path: Path | None = None) -> str:
    where = str(path) if path else "translation pack"
    locale = validate_locale(pack.get("locale"))
    if path is not None and path.stem != locale:
        raise ValueError(f"{where}: filename must match locale {locale!r}")

    strings = pack.get("strings") or {}
    if not isinstance(strings, dict):
        raise ValueError(f"{where}: 'strings' must be an object")
    for source, translation in strings.items():
        if not isinstance(source, str) or not isinstance(translation, str) or not translation:
            raise ValueError(f"{where}: all string translations must be non-empty strings")
        validate_placeholders(source, translation, f"{where}: {source!r}")

    titles = pack.get("dashboard_titles") or {}
    if not isinstance(titles, dict) or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in titles.items()):
        raise ValueError(f"{where}: 'dashboard_titles' must contain non-empty string values")

    passthrough = pack.get("passthrough") or []
    if not isinstance(passthrough, list) or not all(isinstance(item, str) for item in passthrough):
        raise ValueError(f"{where}: 'passthrough' must be an array of strings")

    messages = pack.get("messages") or {}
    if not isinstance(messages, dict):
        raise ValueError(f"{where}: 'messages' must be an object")
    for key, entry in messages.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            raise ValueError(f"{where}: invalid contextual message entry")
        source = entry.get("source")
        translation = entry.get("translation", "")
        status = entry.get("status")
        if not isinstance(source, str) or not isinstance(translation, str) or status not in STATUS_VALUES:
            raise ValueError(f"{where}: invalid contextual message {key!r}")
        if status in {"translated", "needs_review"} and translation:
            validate_placeholders(source, translation, f"{where}: {key}")
    return locale


def discover_packs(directory: Path) -> list[tuple[Path, dict]]:
    directory = Path(directory)
    result: list[tuple[Path, dict]] = []
    seen: dict[str, Path] = {}
    for path in sorted(directory.glob("*.json")):
        pack = load_json(path)
        locale = validate_pack(pack, path)
        if locale in seen:
            raise ValueError(f"duplicate locale {locale!r}: {seen[locale]} and {path}")
        seen[locale] = path
        result.append((path, pack))
    return result


def token(value: object) -> str:
    text = SAFE_TOKEN_RE.sub("_", str(value).strip()).strip("_")
    return text or "unknown"


def list_segment(container_key: str, item: object, index: int) -> str:
    if isinstance(item, dict):
        if container_key == "panels" and item.get("id") is not None:
            return f"panel[{token(item['id'])}]"
        if container_key == "list" and item.get("name"):
            return f"variable[{token(item['name'])}]"
        for discriminator in ("refId", "uid", "name", "id"):
            if item.get(discriminator) not in (None, ""):
                return f"{container_key}[{discriminator}={token(item[discriminator])}]"
    return f"{container_key}[{index}]"


def iter_messages(value: object, context: str, dashboard: str) -> Iterator[Message]:
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_messages(item, f"{context}[{index}]", dashboard)
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
                    yield Message(f"{context}.renameByName[{token(source_name)}]", target, dashboard)
            continue
        if key == "value" and value.get("id") == "displayName" and isinstance(item, str) and item.strip():
            yield Message(f"{context}.value", item, dashboard)
            continue
        if isinstance(item, list):
            for index, child in enumerate(item):
                yield from iter_messages(child, f"{context}.{list_segment(key, child, index)}", dashboard)
        elif isinstance(item, dict):
            yield from iter_messages(item, f"{context}.{key}", dashboard)


def extract_messages(source_dir: Path) -> dict[str, Message]:
    source_dir = Path(source_dir)
    paths = sorted(source_dir.rglob("*.json"))
    if not paths:
        raise ValueError(f"no dashboard JSON files found in {source_dir}")
    result: dict[str, Message] = {}
    for path in paths:
        dashboard_key = path.relative_to(source_dir).with_suffix("").as_posix()
        prefix = f"dashboard.{dashboard_key}"
        for message in iter_messages(load_json(path), prefix, dashboard_key):
            previous = result.get(message.key)
            if previous and previous.source != message.source:
                raise ValueError(f"context key collision for {message.key!r}: {previous.source!r} != {message.source!r}")
            result[message.key] = message
    return dict(sorted(result.items()))


def seed_translation(message: Message, pack: dict) -> tuple[str, str]:
    if message.source in set(pack.get("passthrough") or []):
        return message.source, "passthrough"
    if message.key == f"dashboard.{message.dashboard}.title":
        translated = (pack.get("dashboard_titles") or {}).get(message.dashboard)
        if isinstance(translated, str) and translated:
            validate_placeholders(message.source, translated, message.key)
            return translated, "translated"
    translated = (pack.get("strings") or {}).get(message.source)
    if isinstance(translated, str) and translated:
        validate_placeholders(message.source, translated, message.key)
        return translated, "translated"
    return "", "missing"


def synchronize_catalog(pack: dict, messages: dict[str, Message]) -> tuple[dict, dict[str, int]]:
    validate_pack(pack)
    current = pack.get("messages") or {}
    synchronized: dict[str, dict[str, str]] = {}
    stats = {"translated": 0, "missing": 0, "needs_review": 0, "passthrough": 0, "obsolete": 0}
    for key, message in messages.items():
        old = current.get(key)
        if isinstance(old, dict):
            translation = old.get("translation", "")
            if not isinstance(translation, str):
                translation = ""
            if old.get("source") == message.source:
                status = old.get("status")
                if status not in STATUS_VALUES:
                    status = "translated" if translation else "missing"
            else:
                status = "needs_review" if translation else "missing"
        else:
            translation, status = seed_translation(message, pack)
        if translation and status in {"translated", "needs_review"}:
            try:
                validate_placeholders(message.source, translation, key)
            except ValueError:
                translation = ""
                status = "missing"
        synchronized[key] = {"source": message.source, "translation": translation, "status": status}
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


def resolve_translation(pack: dict, key: str, source: str, dashboard: str) -> str:
    """Resolve a safe translation, falling back to English when uncertain."""
    entry = (pack.get("messages") or {}).get(key)
    if isinstance(entry, dict):
        status = entry.get("status")
        translation = entry.get("translation")
        if status == "translated" and isinstance(translation, str) and translation:
            validate_placeholders(source, translation, key)
            return translation
        if status == "passthrough":
            return source

    if key == f"dashboard.{dashboard}.title":
        title = (pack.get("dashboard_titles") or {}).get(dashboard)
        if isinstance(title, str) and title:
            validate_placeholders(source, title, key)
            return title
    translated = (pack.get("strings") or {}).get(source)
    if isinstance(translated, str) and translated:
        validate_placeholders(source, translated, key)
        return translated
    return source
