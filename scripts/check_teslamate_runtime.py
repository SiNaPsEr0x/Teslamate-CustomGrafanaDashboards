#!/usr/bin/env python3
"""Smoke-test released TeslaMate images against disposable data, never a user DB."""
from __future__ import annotations
import argparse
import base64
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid


def command(*args, check=True, timeout=600):
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if check and result.returncode:
        raise RuntimeError(f"{' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return result


def main(args):
    root = Path(args.root).resolve()
    generated = Path(args.generated).resolve()
    reports = Path(args.report_dir).resolve()
    reports.mkdir(parents=True, exist_ok=True)
    tag = args.release.removeprefix("v")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", tag):
        raise ValueError("Unsupported Docker release tag")
    name = "i18n-" + uuid.uuid4().hex[:10]
    database, grafana, migrate = (name + suffix for suffix in ("-db", "-grafana", "-migrate"))
    runtime = {"release": args.release, "sql": "not run", "grafana": "not run"}
    try:
        command("docker", "network", "create", name)
        command("docker", "run", "-d", "--name", database, "--network", name,
                "--network-alias", "database", "-e", "POSTGRES_USER=teslamate",
                "-e", "POSTGRES_PASSWORD=i18n-test-only", "-e", "POSTGRES_DB=teslamate",
                "postgres:18-trixie")
        for _ in range(60):
            if command("docker", "exec", database, "pg_isready", "-U", "teslamate", check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Disposable PostgreSQL did not become ready")
        env = ["-e", "DATABASE_USER=teslamate", "-e", "DATABASE_PASS=i18n-test-only",
               "-e", "DATABASE_HOST=database", "-e", "DATABASE_NAME=teslamate"]
        image = f"teslamate/teslamate:{tag}"
        command("docker", "run", "--name", migrate, "--network", name, *env,
                "-e", "ENCRYPTION_KEY=i18n-test-only", "-e", "MQTT_HOST=localhost", "--entrypoint", "/opt/app/bin/teslamate",
                image, "eval", "TeslaMate.Release.migrate()", timeout=600)
        runtime["teslamate_image"] = command("docker", "image", "inspect", image,
                                               "--format", "{{json .RepoDigests}}").stdout.strip()
        # Validate original AND translated SQL against the migrated released schema.
        for label, dashboard_root in (("source", root), ("italian", generated.parent)):
            result = command(sys.executable, str(root / "scripts/validate_dashboards.py"),
                             "--root", str(dashboard_root), "--docker", database,
                             check=False, timeout=900)
            (reports / f"sql-{label}.log").write_text(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(f"{label} SQL compatibility failed:\n{result.stdout[-16000:]}\n{result.stderr}")
        runtime["sql"] = "source and Italian queries prepared and planned"
        with tempfile.TemporaryDirectory(prefix="i18n-grafana-") as tmp:
            provisioning = Path(tmp) / "italian.yml"
            provisioning.write_text("apiVersion: 1\nproviders:\n  - name: Italian custom dashboards\n"
                                    "    orgId: 1\n    folder: Italian custom dashboards\n"
                                    "    type: file\n    options:\n      path: /italian-dashboards\n")
            # Grafana runs as an unprivileged user and needs to traverse the directory.
            Path(tmp).chmod(0o755)
            provisioning.chmod(0o644)
            command("docker", "run", "-d", "--name", grafana, "--network", name, *env,
                    "-e", "GF_AUTH_BASIC_ENABLED=true", "-e", "GF_SECURITY_ADMIN_PASSWORD=i18n-test-only",
                    "-p", "127.0.0.1::3000", "--mount",
                    f"type=bind,source={generated},target=/italian-dashboards,readonly",
                    "--mount", f"type=bind,source={provisioning},target=/etc/grafana/provisioning/dashboards/italian.yml,readonly",
                    "--mount", f"type=bind,source={root / 'i18n/teslamate-datasource.yml'},target=/etc/grafana/provisioning/datasources/datasource.yml,readonly",
                    f"teslamate/grafana:{tag}")
            port = command("docker", "port", grafana, "3000/tcp").stdout.strip().rsplit(":", 1)[1]
            base = f"http://127.0.0.1:{port}"
            auth = base64.b64encode(b"admin:i18n-test-only").decode()

            def get(path):
                request = urllib.request.Request(base + path, headers={"Authorization": "Basic " + auth})
                with urllib.request.urlopen(request, timeout=10) as response:
                    return json.load(response)

            expected = {json.loads(p.read_text())["uid"]: json.loads(p.read_text())["title"]
                        for p in generated.glob("*.json")}
            last_error = "Grafana not ready"
            for _ in range(90):
                try:
                    health = get("/api/health")
                    found = {d["uid"]: d["title"] for d in get("/api/search?type=dash-db&limit=5000")}
                    if health.get("database") == "ok" and all(found.get(k) == v for k, v in expected.items()):
                        break
                    last_error = f"Missing/mismatched dashboards: {[k for k,v in expected.items() if found.get(k) != v]}"
                except Exception as exc:
                    last_error = str(exc)
                time.sleep(2)
            else:
                raise RuntimeError(f"Grafana provisioning failed: {last_error}")
            datasource = get("/api/datasources/uid/TeslaMate")
            if datasource.get("type") not in {"postgres", "grafana-postgresql-datasource"}:
                raise RuntimeError(f"Unexpected TeslaMate datasource: {datasource}")
            datasource_health = get("/api/datasources/uid/TeslaMate/health")
            if datasource_health.get("status") != "OK":
                raise RuntimeError(f"Grafana datasource health failed: {datasource_health}")
            runtime["datasource"] = "TeslaMate UID present and database health OK"
            for uid in expected:
                loaded = get(f"/api/dashboards/uid/{uid}")
                if loaded["dashboard"]["title"] != expected[uid]:
                    raise RuntimeError(f"Grafana did not retain Italian title: {uid}")
            runtime.update(grafana=f"{len(expected)} Italian dashboards provisioned and read via API",
                           grafana_version=health.get("version"))
            runtime["grafana_image"] = command("docker", "image", "inspect", f"teslamate/grafana:{tag}",
                                                 "--format", "{{json .RepoDigests}}").stdout.strip()
    finally:
        for container in (database, migrate, grafana):
            logs = command("docker", "logs", container, check=False)
            (reports / f"{container.rsplit('-', 1)[1]}.log").write_text(logs.stdout + logs.stderr)
            command("docker", "rm", "-f", "-v", container, check=False)
        command("docker", "network", "rm", name, check=False)
        (reports / "runtime.json").write_text(json.dumps(runtime, indent=2) + "\n")
    print(json.dumps(runtime, indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--generated", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--report-dir", required=True)
    raise SystemExit(main(parser.parse_args()))
