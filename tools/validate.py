#!/usr/bin/env python3
"""Validate both locale packs, SQL invariants and a single active workflow."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from catalog import entries, validate as validate_catalog

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def raw_sql(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'rawSql': yield item
            else: yield from raw_sql(item)
    elif isinstance(value, list):
        for item in value: yield from raw_sql(item)


def main(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    assert len(list((ROOT / '.github/workflows').glob('*.yml'))) == 1
    assert len(list((ROOT / '.github/workflows').glob('*.yaml'))) == 0
    po = ROOT / 'elixir/priv/gettext/it/LC_MESSAGES/default.po'
    count = validate_catalog(po.read_text())
    active = {(f.get('msgctxt'), f['msgid']) for _, f in entries(po.read_text())}
    required = {(f.get('msgctxt'), f['msgid']) for _, f in entries((ROOT / 'elixir/priv/gettext/default.pot').read_text())}
    if required - active:
        raise ValueError('Catalog is missing msgids from POT: ' + repr(required - active))
    subprocess.run([sys.executable, 'scripts/validate_localization.py'], cwd=ROOT / 'custom', check=True)
    subprocess.run([sys.executable, 'scripts/generate_localized_dashboards.py', '--output', str(output / 'custom/dashboards')],
                   cwd=ROOT / 'custom', check=True)
    validator = load_module('visibility', ROOT / 'custom/scripts/validate_localization.py')
    pack = json.loads((ROOT / 'grafana/i18n/it.json').read_text())
    candidates = set()
    source = ROOT / 'grafana/dashboards'
    paths = sorted(source.rglob('*.json'))
    for path in paths:
        data = json.loads(path.read_text())
        key = path.relative_to(source).with_suffix('').as_posix()
        assert key in pack['dashboard_titles'], 'Missing official dashboard title: ' + key
        local = set()
        validator.collect_visible(data, local)
        local.discard(data.get('title'))
        candidates |= local
    missing = candidates - set(pack['strings']) - set(pack.get('passthrough', []))
    if missing:
        raise ValueError('Missing official Italian strings: ' + repr(sorted(missing)))
    subprocess.run([sys.executable, 'grafana/i18n/generate.py', '--source', str(source),
                    '--translations', str(ROOT / 'grafana/i18n'), '--output', str(output / 'official')], cwd=ROOT, check=True)
    for path in paths:
        data = json.loads(path.read_text())
        relative = path.relative_to(source).with_suffix('').as_posix()
        result = json.loads((output / 'official' / (relative + '.it.json')).read_text())
        assert list(raw_sql(data)) == list(raw_sql(result)), 'SQL changed in ' + relative
        assert result['uid'] == data['uid'] + '-it'
        assert result['title'] == pack['dashboard_titles'][relative]
    info = {'gettext_entries': count, 'official_dashboards': len(paths),
            'custom_dashboards': len(list((output / 'custom/dashboards').glob('*.json'))),
            'official_sql': 'unchanged', 'workflows': 1}
    (output / 'localization.json').write_text(json.dumps(info, indent=2) + '\n')
    print(json.dumps(info, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    main(parser.parse_args().output)
