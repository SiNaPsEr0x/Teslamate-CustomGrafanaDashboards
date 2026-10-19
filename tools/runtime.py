#!/usr/bin/env python3
"""Build and exercise this source distribution in disposable containers."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'checking'}
    prefix = 'sinapse-' + uuid.uuid4().hex[:10]
    project = prefix + '-compose'
    db, migration, app, grafana, tests = [prefix + x for x in ('-db', '-migrate', '-app', '-grafana', '-tests')]

    environment = dict(
        os.environ,
        DATABASE_USER='teslamate',
        DATABASE_PASS='ci-test-password',
        DATABASE_NAME='teslamate',
        ENCRYPTION_KEY='ci-test-encryption-key',
        GRAFANA_ADMIN_USER='admin',
        GRAFANA_ADMIN_PASSWORD='ci-test-password',
        TM_TZ='UTC',
    )
    standalone_environment = dict(os.environ)
    for key in (
        'DATABASE_PASS', 'ENCRYPTION_KEY', 'BASIC_AUTH_PASSWORD',
        'GRAFANA_ADMIN_PASSWORD', 'FQDN_TM', 'LETSENCRYPT_EMAIL',
        'HTTP_PORT', 'HTTPS_PORT', 'MQTT_PORT',
    ):
        standalone_environment.pop(key, None)

    def command(*argv, label=None, check=True, timeout=900, env=None):
        result = subprocess.run(
            [str(a) for a in argv], cwd=ROOT, env=env or environment,
            text=True, capture_output=True, timeout=timeout
        )
        if label:
            (output / (label + '.log')).write_text(result.stdout + result.stderr)
        print(result.stdout[-4000:], end='', flush=True)
        if check and result.returncode:
            raise RuntimeError(f'{argv}\n{result.stdout[-16000:]}\n{result.stderr[-16000:]}')
        return result

    def port(container, internal):
        return command('docker', 'port', container, internal).stdout.strip().rsplit(':', 1)[1]

    def get(url, username=None, password=None):
        headers = {'Accept-Language': 'it-IT,it;q=0.9'}
        if username is not None:
            token = base64.b64encode(f'{username}:{password}'.encode()).decode()
            headers['Authorization'] = 'Basic ' + token
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as response:
            return response.read()

    def retry(fn, seconds=180):
        error = None
        for _ in range(seconds // 2):
            try:
                return fn()
            except Exception as exc:
                error = exc
                time.sleep(2)
        raise RuntimeError('Service did not become ready: ' + str(error))

    def compose(*args, **kwargs):
        return command(
            'docker', 'compose', '-p', project, '-f', 'compose.yml', *args,
            env=standalone_environment, **kwargs
        )

    try:
        model = json.loads(command(
            'docker', 'compose', '-f', 'compose.yml', 'config', '--format', 'json',
            label='compose', env=standalone_environment
        ).stdout)
        bootstrap = model['services']['bootstrap']
        database = model['services']['database']
        proxy = model['services']['proxy']
        teslamate = model['services']['teslamate']
        grafana_service = model['services']['grafana']
        auth = model['services']['basic-auth']
        mosquitto = model['services']['mosquitto']

        assert any(v['target'] == '/var/lib/postgresql' for v in database['volumes'])
        assert any(v['target'] == '/run/sinapse' for v in bootstrap['volumes'])
        assert database['environment']['POSTGRES_PASSWORD_FILE'] == '/run/sinapse/database_pass'
        assert teslamate['image'] == 'ghcr.io/sinapser0x/teslamate:latest'
        assert grafana_service['image'] == teslamate['image']
        assert teslamate['environment']['SINAPSE_SERVICE'] == 'teslamate'
        assert grafana_service['environment']['SINAPSE_SERVICE'] == 'grafana'
        assert teslamate['environment']['CHECK_ORIGIN'] == 'false'
        assert grafana_service['environment']['GF_AUTH_BASIC_ENABLED'] == 'true'
        assert proxy['image'].startswith('traefik:v3.6')
        assert auth['image'].startswith('httpd:2.4')
        assert bootstrap['image'].startswith('alpine:3.22')
        assert not teslamate.get('ports'), 'TeslaMate must only be exposed through Traefik'
        assert not grafana_service.get('ports'), 'Grafana must only be exposed through Traefik'
        assert not mosquitto.get('ports'), 'MQTT must stay internal to the Compose network'
        proxy_ports = {(p['target'], str(p['published']), p['protocol']) for p in proxy['ports']}
        assert (4000, '4000', 'tcp') in proxy_ports
        assert (3000, '3000', 'tcp') in proxy_ports
        assert teslamate['labels']['traefik.http.middlewares.teslamate-auth.basicauth.usersfile'] == '/auth/.htpasswd'
        assert teslamate['labels']['traefik.http.routers.teslamate.entrypoints'] == 'teslamate'
        assert grafana_service['labels']['traefik.http.routers.grafana.entrypoints'] == 'grafana'
        assert any(v['target'] == '/opt/app/import' and v.get('type') == 'volume' for v in teslamate['volumes'])
        compose_text = (ROOT / 'compose.yml').read_text()
        assert ':?' not in compose_text, 'compose.yml must not require external variables'
        report['compose'] = (
            'validated standalone single-YAML stack with persistent generated secrets, '
            'one shared prebuilt image, protected TeslaMate, Grafana login and internal MQTT'
        )

        # Pull only third-party runtime images. The unified image is built from this exact source tree below.
        for image in sorted({bootstrap['image'], auth['image'], proxy['image'], database['image'], mosquitto['image']}):
            command('docker', 'pull', image, label='pull-' + image.split(':')[0].split('/')[-1], timeout=900)

        command('docker', 'build', '-t', teslamate['image'], '-f', 'Dockerfile.unified', '.',
                label='build-unified', timeout=2700)
        report['builds'] = 'single unified image built with TeslaMate and localized Grafana from this patched source tree'

        # Keep the exhaustive application/database checks used by the distribution pipeline.
        command('docker', 'network', 'create', prefix)
        command('docker', 'run', '-d', '--name', db, '--network', prefix, '--network-alias', 'database',
                '-e', 'POSTGRES_USER=teslamate', '-e', 'POSTGRES_PASSWORD=ci-test-password',
                '-e', 'POSTGRES_DB=teslamate', database['image'])
        retry(lambda: subprocess.run(
            ['docker', 'exec', db, 'pg_isready', '-h', '127.0.0.1', '-U', 'teslamate'],
            check=True, capture_output=True
        ))
        env = [
            '-e', 'DATABASE_USER=teslamate', '-e', 'DATABASE_PASS=ci-test-password',
            '-e', 'DATABASE_NAME=teslamate', '-e', 'DATABASE_HOST=database',
            '-e', 'ENCRYPTION_KEY=ci-test-encryption-key', '-e', 'DISABLE_MQTT=true'
        ]
        command(
            'docker', 'run', '--name', tests, '--network', prefix,
            '--user', f'{os.getuid()}:{os.getgid()}', '-e', 'HOME=/tmp',
            '-e', 'HEX_HOME=/tmp/.hex', '-e', 'MIX_HOME=/tmp/.mix', *env,
            '-e', 'DATABASE_NAME=teslamate_test', '-e', 'MIX_ENV=test',
            '-e', 'ELIXIR_ASSERT_TIMEOUT=1000',
            '--mount', f'type=bind,source={ROOT},target=/repo', '-w', '/repo/elixir',
            'elixir:1.20.3-otp-29', 'bash', '-euc',
            'mix local.hex --force; mix local.rebar --force; mix deps.get; '
            'mix compile --warnings-as-errors; '
            'mix format --check-formatted test/teslamate_web/gettext_i18n_test.exs '
            'test/teslamate_web/grafana_i18n_test.exs; mix test --warnings-as-errors',
            label='elixir-tests', timeout=1800
        )
        report['elixir'] = 'full mix test --warnings-as-errors, including Italian plural and Grafana locale tests'
        command(
            'docker', 'run', '--name', migration, '--network', prefix, '--user', '10000:10001',
            '-w', '/opt/app', *env, '--entrypoint', '/opt/app/bin/teslamate', teslamate['image'],
            'eval', 'TeslaMate.Release.migrate()', label='migrations'
        )
        for name, directory in [('custom-source', ROOT / 'custom'), ('custom-italian', output / 'custom')]:
            command(
                sys.executable, ROOT / 'custom/scripts/validate_dashboards.py', '--root', directory,
                '--docker', db, '--strict', label='sql-' + name, timeout=900
            )
        report['sql'] = 'original and Italian custom queries prepared and planned with zero warnings against patched app migrations'

        command(
            'docker', 'run', '-d', '--name', app, '--network', prefix, '--user', '10000:10001',
            *env, '-e', 'SINAPSE_SERVICE=teslamate', '-e', 'HTTP_BINDING_ADDRESS=0.0.0.0',
            '-p', '127.0.0.1::4000', teslamate['image']
        )
        app_url = 'http://127.0.0.1:' + port(app, '4000/tcp')
        body = retry(lambda: get(app_url + '/')).decode()
        assert 'TeslaMate' in body
        report['app'] = 'TeslaMate mode from unified image boots and serves HTTP'

        command(
            'docker', 'run', '-d', '--name', grafana, '--network', prefix, '--user', '472:0',
            *env, '-e', 'SINAPSE_SERVICE=grafana', '-e', 'GF_AUTH_BASIC_ENABLED=true',
            '-e', 'GF_SECURITY_ADMIN_PASSWORD=ci-test-password', '-p', '127.0.0.1::3000',
            grafana_service['image']
        )
        base = 'http://127.0.0.1:' + port(grafana, '3000/tcp')
        expected = {}
        for folder in [output / 'official', output / 'custom/dashboards']:
            for path in folder.rglob('*.json'):
                data = json.loads(path.read_text())
                if data['uid'] in expected:
                    raise ValueError('Duplicate localized UID')
                expected[data['uid']] = data['title']

        def provisioned():
            health = json.loads(get(base + '/api/health'))
            found = {
                d['uid']: d['title'] for d in json.loads(
                    get(base + '/api/search?type=dash-db&limit=5000', 'admin', 'ci-test-password')
                )
            }
            assert health['database'] == 'ok'
            assert all(found.get(uid) == title for uid, title in expected.items()), 'Dashboard provisioning incomplete'
            return health

        health = retry(provisioned)
        ds = json.loads(get(base + '/api/datasources/uid/TeslaMate/health', 'admin', 'ci-test-password'))
        assert ds['status'] == 'OK', ds
        for uid, title in expected.items():
            data = json.loads(get(base + '/api/dashboards/uid/' + uid, 'admin', 'ci-test-password'))
            assert data['dashboard']['title'] == title

        # Exercise the actual user-facing compose.yml with no .env and no injected secrets.
        compose('up', '-d', '--pull', 'never', label='compose-up', timeout=900)
        bootstrap_logs = compose('logs', '--no-color', 'bootstrap', label='bootstrap').stdout
        tm_match = re.search(r'TeslaMate\s+-> user: teslamate\s+password: (\S+)', bootstrap_logs)
        gf_match = re.search(r'Grafana\s+-> user: admin\s+password: (\S+)', bootstrap_logs)
        assert tm_match and gf_match, 'Generated login credentials were not printed by bootstrap'
        tm_password, gf_password = tm_match.group(1), gf_match.group(1)

        tm_url = 'http://127.0.0.1:4000/'
        gf_url = 'http://127.0.0.1:3000'

        def teslamate_through_proxy():
            try:
                get(tm_url)
            except urllib.error.HTTPError as exc:
                assert exc.code == 401
            else:
                raise AssertionError('TeslaMate proxy must reject unauthenticated requests')
            body = get(tm_url, 'teslamate', tm_password).decode()
            assert 'TeslaMate' in body
            return True

        retry(teslamate_through_proxy)

        def grafana_through_proxy():
            health_data = json.loads(get(gf_url + '/api/health'))
            assert health_data['database'] == 'ok'
            user = json.loads(get(gf_url + '/api/user', 'admin', gf_password))
            assert user['login'] == 'admin'
            datasource = json.loads(get(gf_url + '/api/datasources/uid/TeslaMate/health', 'admin', gf_password))
            assert datasource['status'] == 'OK'
            return health_data

        stack_health = retry(grafana_through_proxy)

        # Re-run bootstrap against the same secret volume and prove credentials are persistent.
        repeat = compose('run', '--rm', '--no-deps', 'bootstrap', label='bootstrap-repeat').stdout
        assert tm_password in repeat and gf_password in repeat, 'Generated credentials changed across restarts'

        report.update(
            status='passed', grafana_version=health['version'], localized_dashboards=len(expected),
            datasource='TeslaMate UID and database health OK',
            standalone=(
                'compose.yml starts without .env, generates persistent credentials, protects TeslaMate, '
                f'and serves Grafana {stack_health["version"]} on the documented ports'
            )
        )
    finally:
        compose('down', '-v', '--remove-orphans', check=False, timeout=300, label='compose-down')
        for container in (app, grafana, migration, tests, db):
            logs = command('docker', 'logs', container, check=False)
            (output / (container.rsplit('-', 1)[1] + '-container.log')).write_text(logs.stdout + logs.stderr)
            command('docker', 'rm', '-f', '-v', container, check=False)
        command('docker', 'network', 'rm', prefix, check=False)
        (output / 'runtime.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    main(parser.parse_args().output)
