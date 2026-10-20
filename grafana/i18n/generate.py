#!/usr/bin/env python3
"""Generate Italian official dashboards with stable SQL and localized navigation."""
import argparse
import copy
import json
from pathlib import Path
import re
import localizer


def links(value, uid_map, key=''):
    if key in {'rawSql', 'query', 'definition'}:
        return value
    if isinstance(value, dict):
        return {k: links(v, uid_map, k) for k, v in value.items()}
    if isinstance(value, list):
        return [links(v, uid_map, key) for v in value]
    if isinstance(value, str) and key in {'url', 'linkUrl'}:
        for before, after in uid_map.items():
            value = value.replace('/d/' + before, '/d/' + after)
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--translations', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    source, out = Path(args.source), Path(args.output)
    paths = sorted(source.rglob('*.json'))
    if not paths:
        raise ValueError('No official source dashboards')
    for pack_path in Path(args.translations).glob('*.json'):
        pack = json.loads(pack_path.read_text())
        locale = pack['locale']
        uid_map = {json.loads(p.read_text())['uid']: json.loads(p.read_text())['uid'] + '-' + locale
                   for p in paths}
        for path in paths:
            key = path.relative_to(source).with_suffix('').as_posix()
            # The localized internal Home dashboard shares the original title
            # and folder. Grafana rejects both as duplicate provisioning entries.
            if key == 'internal/home':
                continue
            original = json.loads(path.read_text())
            result = localizer.localize_dashboard(original, key, pack)
            result = links(result, uid_map)
            result['uid'] = uid_map[original['uid']]
            result['tags'] = [f'tesla-{locale}' if t == 'tesla' else t for t in result.get('tags', [])]
            target = out / (key + '.' + locale + '.json')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(f'Generated {len(paths)} official dashboards per language')


if __name__ == '__main__':
    main()
