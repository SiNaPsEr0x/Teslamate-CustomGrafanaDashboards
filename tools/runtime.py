#!/usr/bin/env python3
"""Build and exercise this source distribution in disposable containers."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'checking'}
    prefix = 'sinapse-' + uuid.uuid4().hex[:10]
    db, migration, app, grafana, tests = [prefix + x for x in ('-db', '-migrate', '-app', '-grafana', '-tests')]
    environment = dict(
        os.environ,
        DATABASE_USER='teslamate',
        DATABASE_PASS='ci-test-password',
        DATABASE_NAME='teslamate',
        ENCRYPTION_KEY='ci-test-encryption-key',
        GRAFANA_ADMIN_USER='admin',
        GRAFANA_ADMIN_PASSWORD='ci-test-password',
        FQDN_TM='teslamate.example.invalid',
        TM_TZ='UTC',
        LETSENCRYPT_EMAIL='ci@example.invalid',
        BASIC_AUTH_USER='admin',
        BASIC_AUTH_PASSWORD='ci-test-password',
        MQTT_PORT='1883',
    )

    def command(*argv, label=None, check=True, timeout=900):
        result = subprocess.run([str(a) for a in argv], cwd=ROOT, env=environment,
                                text=True, capture_output=True, timeout=timeout)
        if label:
            (output / (label + '.log')).write_text(result.stdout + result.stderr)
        print(result.stdout[-4000:], end='', flush=True)
        if check and result.returncode:
            raise RuntimeError(f'{argv}\n{result.stdout[-16000:]}\n{result.stderr[-16000:]}')
        return result

    def port(container, internal):
        return command('docker', 'port', container, internal).stdout.strip().rsplit(':', 1)[1]

    def get(url, auth=False):
        headers = {'Accept-Language': 'it-IT,it;q=0.9'}
        if auth:
            headers['Authorization'] = 'Basic ' + base64.b64encode(b'admin:ci-test-password').decode()
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as response:
            return response.read()

    def retry(fn, seconds=120):
        error = None
        for _ in range(seconds // 2):
            try:
                return fn()
            except Exception as exc:
                error = exc
                time.sleep(2)
        raise RuntimeError('Service did not become ready: ' + str(error))

    try:
        model = json.loads(command('docker', 'compose', '-f', 'compose.yml', 'config', '--format', 'json',
                                   label='compose').stdout)
        database = model['services']['database']
        proxy = model['services']['proxy']
        teslamate = model['services']['teslamate']
        grafana_service = model['services']['grafana']
        auth = model['services']['basic-auth']

        assert any(v['target'] == '/var/lib/postgresql' for v in database['volumes'])
        assert teslamate['build']['context'] == str(ROOT)
        assert grafana_service['build']['dockerfile'] == 'grafana/Dockerfile'
        assert proxy['image'].startswith('traefik:v3.6')
        assert auth['image'].startswith('httpd:2.4')
        assert not teslamate.get('ports'), 'TeslaMate must only be exposed through Traefik'
        assert not grafana_service.get('ports'), 'Grafana must only be exposed through Traefik'
        assert teslamate['environment']['CHECK_ORIGIN'] == 'true'
        assert teslamate['environment']['VIRTUAL_HOST'] == environment['FQDN_TM']
        assert grafana_service['environment']['GF_SERVER_ROOT_URL'] == 'https://%(domain)s/grafana'
        assert grafana_service['environment']['GF_SERVER_SERVE_FROM_SUB_PATH'] == 'true'
        assert teslamate['labels']['traefik.http.middlewares.teslamate-auth.basicauth.usersfile'] == '/auth/.htpasswd'
        assert grafana_service['labels']['traefik.http.routers.grafana.tls.certresolver'] == 'tmhttpchallenge'
        report['compose'] = (
            'validated all-in-one Traefik HTTPS, generated Basic Auth, integrated builds '
            'and PostgreSQL 18 volume layout'
        )

        command('docker', 'compose', '-f', 'compose.yml', 'build', label='build', timeout=2700)
        report['builds'] = 'TeslaMate and Grafana built from this patched source tree'
        command('docker', 'network', 'create', prefix)
        command('docker', 'run', '-d', '--name', db, '--network', prefix, '--network-alias', 'database',
                '-e', 'POSTGRES_USER=teslamate', '-e', 'POSTGRES_PASSWORD=ci-test-password',
                '-e', 'POSTGRES_DB=teslamate', database['image'])
        retry(lambda: subprocess.run(['docker', 'exec', db, 'pg_isready', '-h', '127.0.0.1', '-U', 'teslamate'],
                                     check=True, capture_output=True))
        env = ['-e', 'DATABASE_USER=teslamate', '-e', 'DATABASE_PASS=ci-test-password', '-e', 'DATABASE_NAME=teslamate',
               '-e', 'DATABASE_HOST=database', '-e', 'ENCRYPTION_KEY=ci-test-encryption-key', '-e', 'DISABLE_MQTT=true']
        # Run all available Elixir tests, including the exact Italian plural regression.
        command('docker', 'run', '--name', tests, '--network', prefix, '--user', f'{os.getuid()}:{os.getgid()}',
                '-e', 'HOME=/tmp', '-e', 'HEX_HOME=/tmp/.hex', '-e', 'MIX_HOME=/tmp/.mix', *env,
                '-e', 'DATABASE_NAME=teslamate_test', '-e', 'MIX_ENV=test', '-e', 'ELIXIR_ASSERT_TIMEOUT=1000',
                '--mount', f'type=bind,source={ROOT},target=/repo', '-w', '/repo/elixir',
                'elixir:1.20.3-otp-29', 'bash', '-euc',
                'mix local.hex --force; mix local.rebar --force; mix deps.get; mix compile --warnings-as-errors; '
                'mix format --check-formatted test/teslamate_web/gettext_i18n_test.exs test/teslamate_web/grafana_i18n_test.exs; '
                'mix test --warnings-as-errors', label='elixir-tests', timeout=1800)
        report['elixir'] = 'full mix test --warnings-as-errors, including Italian plural and Grafana locale tests'
        command('docker', 'run', '--name', migration, '--network', prefix, *env,
                '--entrypoint', '/opt/app/bin/teslamate', 'sinapse/teslamate:local',
                'eval', 'TeslaMate.Release.migrate()', label='migrations')
        for name, directory in [('custom-source', ROOT / 'custom'), ('custom-italian', output / 'custom')]:
            command(sys.executable, ROOT / 'custom/scripts/validate_dashboards.py', '--root', directory,
                    '--docker', db, label='sql-' + name, timeout=900)
        report['sql'] = 'original and Italian custom queries prepared and planned against patched app migrations'
        command('docker', 'run', '-d', '--name', app, '--network', prefix, *env,
                '-e', 'HTTP_BINDING_ADDRESS=0.0.0.0', '-p', '127.0.0.1::4000', 'sinapse/teslamate:local')
        app_url = 'http://127.0.0.1:' + port(app, '4000/tcp')
        body = retry(lambda: get(app_url + '/')).decode()
        assert 'TeslaMate' in body
        report['app'] = 'patched application boots and serves HTTP'
        command('docker', 'run', '-d', '--name', grafana, '--network', prefix, *env,
                '-e', 'GF_AUTH_BASIC_ENABLED=true', '-e', 'GF_SECURITY_ADMIN_PASSWORD=ci-test-password',
                '-p', '127.0.0.1::3000', 'sinapse/teslamate-grafana:local')
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
            found = {d['uid']: d['title'] for d in json.loads(get(base + '/api/search?type=dash-db&limit=5000', True))}
            assert health['database'] == 'ok'
            assert all(found.get(uid) == title for uid, title in expected.items()), 'Dashboard provisioning incomplete'
            return health

        health = retry(provisioned)
        ds = json.loads(get(base + '/api/datasources/uid/TeslaMate/health', True))
        assert ds['status'] == 'OK', ds
        for uid, title in expected.items():
            data = json.loads(get(base + '/api/dashboards/uid/' + uid, True))
            assert data['dashboard']['title'] == title
        report.update(status='passed', grafana_version=health['version'],
                      localized_dashboards=len(expected), datasource='TeslaMate UID and database health OK')
    finally:
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
