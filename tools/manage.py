#!/usr/bin/env python3
"""Prepare, test and publish the unified distribution as a single transaction."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback
from catalog import overlay, validate as validate_catalog

REPO = 'SiNaPsEr0x/Teslamate-CustomGrafanaDashboards'
OFFICIAL = 'teslamate-org/teslamate'
CUSTOMS = 'jheredianet/Teslamate-CustomGrafanaDashboards'
LANGUAGE_FORK = 'SiNaPsEr0x/teslamate'
LANGUAGE_SNAPSHOT = '1f0d1235a6838c8c5adb5ebc1143e82eac768422'
CUSTOM_SNAPSHOT = 'e82f3b22039d355a7c714689079829cb2035859a'
BASE_RELEASE = '33d200b2fba9d5138803916a788cef5eae31b1aa'
DASHBOARD_PATCH = '40910165'
STATE = '.github/unified-state.json'
WORKFLOW = '.github/workflows/sync-italian-localization.yml'
KEEP = ['tools', 'config', 'compose.yml', '.env.example', 'README.md', '.github/pull.yml', WORKFLOW]


def run(*argv, cwd=None, check=True, timeout=1200, input=None, env=None):
    result = subprocess.run([str(a) for a in argv], cwd=cwd, input=input, env=env,
                            capture_output=True, text=True, timeout=timeout)
    if result.stdout:
        print(result.stdout, end='', flush=True)
    if check and result.returncode:
        raise RuntimeError(f'Command failed: {argv}\n{result.stdout[-14000:]}\n{result.stderr[-14000:]}')
    return result


def git(root, *argv, check=True):
    return run('git', *argv, cwd=root, check=check).stdout.strip()


def api(path, payload=None, method=None):
    argv = ['gh', 'api', path]
    if payload is not None:
        argv += ['--method', method or 'POST', '--input', '-']
    return json.loads(run(*argv, input=json.dumps(payload) if payload is not None else None).stdout)


def issue(title, body):
    pages = json.loads(run('gh', 'api', '--paginate', '--slurp', f'repos/{REPO}/issues?state=open&per_page=100').stdout)
    for page in pages:
        for item in page:
            if item.get('title') == title and 'pull_request' not in item:
                api(f"repos/{REPO}/issues/{item['number']}", {'body': body[:60000]}, 'PATCH')
                return item['html_url']
    return api(f'repos/{REPO}/issues', {'title': title, 'body': body[:60000]})['html_url']


def ancestor(root, old, new):
    result = run('git', 'merge-base', '--is-ancestor', old, new, cwd=root, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    return result.returncode == 0


def fetch_release(root, repo, name):
    release = api(f'repos/{repo}/releases/latest')
    tag = release['tag_name']
    if release.get('draft') or release.get('prerelease'):
        raise ValueError('Expected a stable published release')
    git(root, 'check-ref-format', 'refs/tags/' + tag)
    git(root, 'fetch', '--no-tags', f'https://github.com/{repo}.git',
        f'refs/tags/{tag}:refs/unified/{name}/{tag}')
    return {'release': tag, 'commit': git(root, 'rev-parse', f'refs/unified/{name}/{tag}^{{commit}}'),
            'release_id': release['id'], 'url': release['html_url']}


def merge_release(root, old, new, prefix=None):
    if not ancestor(root, old, new):
        raise RuntimeError('Upstream history regressed or diverged')
    if ancestor(root, new, 'HEAD'):
        return False
    args = ['merge', '--no-ff', '--no-edit']
    if prefix:
        args += ['-Xsubtree=' + prefix]
    result = run('git', *args, new, cwd=root, check=False)
    if result.returncode:
        conflicts = git(root, 'diff', '--name-only', '--diff-filter=U')
        git(root, 'merge', '--abort')
        raise RuntimeError('Merge conflict, candidate not published:\n' + conflicts + '\n' + result.stderr)
    return True


def archive(root, sha, target):
    target.mkdir(parents=True, exist_ok=True)
    # Git archives contain only the reviewed repository snapshot, never host files.
    result = subprocess.run(['git', 'archive', sha], cwd=root, capture_output=True, check=True)
    subprocess.run(['tar', '-x', '-C', str(target)], input=result.stdout, check=True)


def bootstrap(root, work, start, controller, temporary):
    git(root, 'fetch', '--no-tags', f'https://github.com/{LANGUAGE_FORK}.git', LANGUAGE_SNAPSHOT)
    git(root, 'fetch', '--no-tags', 'origin', CUSTOM_SNAPSHOT)
    seed = temporary / 'language-seed'
    git(root, 'worktree', 'add', '--detach', str(seed), BASE_RELEASE)
    try:
        git(seed, 'cherry-pick', DASHBOARD_PATCH)
        po = seed / 'elixir/priv/gettext/it/LC_MESSAGES/default.po'
        original = git(root, 'show', LANGUAGE_SNAPSHOT + ':elixir/priv/gettext/it/LC_MESSAGES/default.po')
        po.write_text(overlay(po.read_text(), original))
        validate_catalog(po.read_text())
        test = 'elixir/test/teslamate_web/gettext_i18n_test.exs'
        (seed / test).write_text(git(root, 'show', LANGUAGE_SNAPSHOT + ':' + test) + '\n')
        git(seed, 'add', 'elixir/priv/gettext/it/LC_MESSAGES/default.po', test)
        git(seed, 'commit', '-m', 'i18n(it): apply complete catalog and strict Italian plural validation')
        seed_sha = git(seed, 'rev-parse', 'HEAD')
        # Replace only the disposable candidate tree; all remote history is retained.
        git(work, 'read-tree', '--reset', '-u', seed_sha)
        git(work, 'read-tree', '--prefix=custom/', '-u', CUSTOM_SNAPSHOT)
        (work / 'docs').mkdir(exist_ok=True)
        shutil.copyfile(work / 'README.md', work / 'docs/TESLAMATE-UPSTREAM.md')
        for path in KEEP:
            source, destination = controller / path, work / path
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
        normalize(work)
        git(work, 'add', '-A')
        tree = git(work, 'write-tree')
        commit = git(work, 'commit-tree', tree, '-p', start, '-p', seed_sha, '-p', CUSTOM_SNAPSHOT,
                     '-m', 'feat: unify stable TeslaMate, Italian patches and Custom Dashboards on main')
        git(work, 'update-ref', '--no-deref', 'HEAD', commit)
        return {'schema': 1, 'language_snapshot': LANGUAGE_SNAPSHOT,
                'language_source_base': BASE_RELEASE, 'custom_snapshot': CUSTOM_SNAPSHOT,
                'teslamate': {'release': 'v4.3.0', 'commit': BASE_RELEASE, 'release_id': 399242545},
                'customs': {'release': 'v2026.10.15', 'commit': 'f473c3eb7b99d03b52a921c9c6f4da4ebcc2f8b8', 'release_id': 413657803}}
    finally:
        git(root, 'worktree', 'remove', '--force', str(seed))


def normalize(root):
    (root / '.github/pull.yml').write_text('version: \"1\"\nrules: []\n')
    workflows = root / '.github/workflows'
    for path in workflows.iterdir():
        if path.name != Path(WORKFLOW).name:
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink()
    # Keep a single safe localizer implementation for official and custom panels.
    shutil.copyfile(root / 'custom/scripts/generate_localized_dashboards.py', root / 'grafana/i18n/localizer.py')
    shutil.copyfile(root / 'tools/official_generator.py', root / 'grafana/i18n/generate.py')
    dockerfile = root / 'grafana/Dockerfile'
    text = dockerfile.read_text()
    if '# SINAPSE_CUSTOM_BUILD' not in text:
        stage = '''# SINAPSE_CUSTOM_BUILD
FROM python:3.13-alpine AS sinapse-custom
WORKDIR /src
COPY custom/dashboards /src/dashboards
COPY custom/i18n/it.json /src/it.json
COPY custom/scripts/generate_localized_dashboards.py /src/generate.py
RUN python /src/generate.py --source /src/dashboards --pack /src/it.json --output /out

'''
        text = stage + text
    if '# SINAPSE_CUSTOM_INSTALL' not in text:
        text += '''
# SINAPSE_CUSTOM_INSTALL
COPY --from=sinapse-custom /out/ /custom_dashboards/
COPY config/grafana/custom.yml /etc/grafana/provisioning/dashboards/sinapse-custom.yml
COPY config/grafana/datasource.yml /etc/grafana/provisioning/datasources/datasource.yml
COPY custom/LICENSE /usr/share/doc/teslamate-custom/LICENSE
'''
    dockerfile.write_text(text)
    context_ignore = root / 'grafana/Dockerfile.dockerignore'
    ignored = context_ignore.read_text() if context_ignore.exists() else ''
    if '# SINAPSE_CUSTOM_CONTEXT' not in ignored:
        context_ignore.write_text(ignored + "\n# SINAPSE_CUSTOM_CONTEXT\n!custom\ncustom/*\n!custom/dashboards\n!custom/dashboards/**\n!custom/i18n\ncustom/i18n/*\n!custom/i18n/it.json\n!custom/scripts\ncustom/scripts/*\n!custom/scripts/generate_localized_dashboards.py\n!custom/LICENSE\n!config\n!config/**\n")
    app_ignore = root / '.dockerignore'
    ignored = app_ignore.read_text() if app_ignore.exists() else ''
    if '# SINAPSE_SECRETS' not in ignored:
        app_ignore.write_text(ignored + "\n# SINAPSE_SECRETS\n.env\n.env.*\n.unified-output/\ncustom/screenshots/\n")
    ignore = root / '.gitignore'
    text = ignore.read_text() if ignore.exists() else ''
    extra = '\n# Unified distribution local secrets and generated artifacts\n.env\n.unified-output/\n__pycache__/\n*.pyc\n'
    if '# Unified distribution local secrets' not in text:
        ignore.write_text(text + extra)


def translation_snapshot(root):
    packs = {}
    for relative in ['custom/i18n/it.json', 'grafana/i18n/it.json']:
        pack = json.loads((root / relative).read_text())
        packs[relative] = {section: pack.get(section, {}) for section in ('strings', 'dashboard_titles')}
    packs['gettext'] = {(f.get('msgctxt'), f['msgid']): {k: v for k, v in f.items() if k.startswith('msgstr')}
                        for _, f in __import__('catalog').entries((root / 'elixir/priv/gettext/it/LC_MESSAGES/default.po').read_text())
                        if f['msgid']}
    return packs


def preserve_translations(before, after):
    for path, sections in before.items():
        if path == 'gettext':
            for key, forms in sections.items():
                if key in after[path] and after[path][key] != forms:
                    raise ValueError('Existing Italian gettext translation changed: ' + repr(key))
            continue
        for section, values in sections.items():
            for source, target in values.items():
                if after.get(path, {}).get(section, {}).get(source) != target:
                    raise ValueError(f'Italian translation lost or changed: {path}: {source}')


def publish(root, expected):
    current = git(root, 'ls-remote', 'origin', 'refs/heads/main').split()[0]
    if current != expected:
        raise RuntimeError(f'Concurrent main update: expected {expected}, found {current}')
    git(root, 'push', 'origin', 'HEAD:refs/heads/main')


def main(args):
    root, output = Path(args.root).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'checking', 'runtime': 'not run'}
    stage = 'resolve upstream releases'
    published = False
    try:
        git(root, 'config', 'user.name', 'github-actions[bot]')
        git(root, 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
        start = git(root, 'rev-parse', 'HEAD')
        report['starting_commit'] = start
        latest = {name: fetch_release(root, repo, name) for name, repo in [('teslamate', OFFICIAL), ('customs', CUSTOMS)]}
        report['latest'] = latest
        with tempfile.TemporaryDirectory(prefix='sinapse-unified-') as tmp:
            temporary = Path(tmp)
            work = temporary / 'candidate'
            git(root, 'worktree', 'add', '--detach', str(work), start)
            try:
                state_path = root / STATE
                initial = not state_path.exists()
                if initial:
                    stage = 'unify source histories and Italian patches'
                    state = bootstrap(root, work, start, root, temporary)
                else:
                    state = json.loads(state_path.read_text())
                report['bootstrap'] = initial
                before_translations = translation_snapshot(work)
                stage = 'merge upstream releases'
                for name, repo in [('teslamate', OFFICIAL), ('customs', CUSTOMS)]:
                    old = state[name]
                    # Verify the old release still resolves to its recorded immutable commit.
                    git(root, 'fetch', '--no-tags', f'https://github.com/{repo}.git',
                        f"refs/tags/{old['release']}:refs/unified/previous-{name}/{old['release']}")
                    resolved = git(root, 'rev-parse', f"refs/unified/previous-{name}/{old['release']}^{{commit}}")
                    if resolved != old['commit']:
                        raise RuntimeError(f'{name} previously recorded tag was moved')
                    changed = git(root, 'diff', '--name-only', old['commit'], latest[name]['commit']).splitlines()
                    report[name + '_changed_files'] = changed
                    if changed:
                        (output / (name + '-upstream.diff')).write_text(git(root, 'diff', old['commit'], latest[name]['commit']))
                    merge_release(work, old['commit'], latest[name]['commit'], 'custom' if name == 'customs' else None)
                stage = 'preserve and validate Italian localization'
                normalize(work)
                preserve_translations(before_translations, translation_snapshot(work))
                run(sys.executable, 'tools/validate.py', '--output', str(output), cwd=work)
                run(sys.executable, '-m', 'unittest', 'discover', '-s', 'tools/tests', '-v', cwd=work)
                run(sys.executable, '-m', 'unittest', 'discover', '-s', 'custom/tests', '-v', cwd=work)
                stage = 'build, Elixir tests and runtime compatibility'
                if args.runtime:
                    run(sys.executable, 'tools/runtime.py', '--output', str(output), cwd=work, timeout=5100)
                    report['runtime'] = 'source builds, Elixir tests, Compose, SQL, app and Grafana passed'
                elif args.publish:
                    raise RuntimeError('Publication requires --runtime')
                if report['teslamate_changed_files'] and args.publish:
                    report['review_issue'] = issue('Review unified TeslaMate ' + latest['teslamate']['release'],
                        'Upstream release: ' + latest['teslamate']['url'] + '\n\nChanged files:\n' +
                        '\n'.join('- `' + p + '`' for p in report['teslamate_changed_files']) +
                        '\n\nAutomated source build, tests and runtime checks passed. Review the attached diff for changes not covered by smoke tests.\nRun: ' + run_url())
                state.update(latest)
                state['validation'] = report['runtime']
                (work / STATE).write_text(json.dumps(state, indent=2) + '\n')
                git(work, 'add', '-A')
                if run('git', 'diff', '--cached', '--quiet', cwd=work, check=False).returncode:
                    git(work, 'commit', '-m', 'chore: record validated unified distribution and upstream releases')
                report['candidate_commit'] = git(work, 'rev-parse', 'HEAD')
                if args.publish:
                    stage = 'publish main'
                    publish(work, start)
                    published = True
                    if initial:
                        stage = 'archive historical branches'
                        refs = git(root, 'ls-remote', '--heads', 'origin').splitlines()
                        archives = {}
                        for row in refs:
                            sha, ref = row.split()
                            branch = ref.removeprefix('refs/heads/')
                            if branch == 'main': continue
                            git(root, 'fetch', '--no-tags', 'origin', ref)
                            tag = 'archive/2026-10-18/' + branch
                            git(root, 'push', 'origin', sha + ':refs/tags/' + tag)
                            archives[branch] = {'commit': sha, 'tag': tag}
                        report['archived_branches'] = archives
                report['status'] = 'passed'
            finally:
                git(root, 'worktree', 'remove', '--force', str(work))
    except Exception as exc:
        report.update(status='failed', failed_stage=stage, error=str(exc)[-28000:], published=published)
        traceback.print_exc()
        if args.publish:
            try:
                key = hashlib.sha256((stage + json.dumps(report.get('latest', {}), sort_keys=True)).encode()).hexdigest()[:10]
                report['issue'] = issue('Unified Italian distribution blocked: ' + stage + ' [' + key + ']',
                    'Run: ' + run_url() + '\n\n' + ('Main was already published; archive cleanup remains pending.' if published else 'The candidate was not published; main is unchanged.') +
                    '\n\n```json\n' + json.dumps(report, indent=2) + '\n```')
            except Exception as err:
                report['issue_error'] = str(err)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write('## SiNaPsE unified TeslaMate\n\nStatus: **' + report['status'] + '**\n\n' + report['runtime'] + '\n')
    return int(report['status'] != 'passed')


def run_url():
    return f"https://github.com/{REPO}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.')
    parser.add_argument('--output', required=True)
    parser.add_argument('--runtime', action='store_true')
    parser.add_argument('--publish', action='store_true')
    raise SystemExit(main(parser.parse_args()))
