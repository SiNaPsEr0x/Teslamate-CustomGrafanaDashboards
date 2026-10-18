#!/usr/bin/env python3
"""Transactional release sync: merge, validate, then ordinary fast-forward push."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

CUSTOMS = "jheredianet/Teslamate-CustomGrafanaDashboards"
TESLAMATE = "teslamate-org/teslamate"
BRANCH = "i18n/italian-localization-upstream"
STATE = ".github/i18n-upstream-state.json"
SENSITIVE = re.compile(
    r"(^|/)(?:priv/repo/|grafana/|Dockerfile[^/]*$|[^/]*compose[^/]*\.ya?ml$|"
    r"entrypoint[^/]*|mix\.(?:exs|lock)$|config/|installation/|lib/teslamate/(?:log|repo|settings))"
)


def run(*args, cwd=None, check=True, timeout=600, input=None):
    result = subprocess.run(args, cwd=cwd, text=True, input=input,
                            capture_output=True, timeout=timeout)
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.returncode and check:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}\n"
                           f"{result.stdout[-18000:]}\n{result.stderr[-18000:]}")
    return result


def git(root, *args, check=True):
    return run("git", *args, cwd=root, check=check).stdout.strip()


def api(path, payload=None):
    args = ["gh", "api", path]
    if payload is not None:
        args += ["--method", "POST", "--input", "-"]
    return json.loads(run(*args, input=json.dumps(payload) if payload else None).stdout)


def release(root, repo, namespace):
    data = api(f"repos/{repo}/releases/latest")
    tag = data["tag_name"]
    if data.get("draft") or data.get("prerelease") or not tag:
        raise RuntimeError(f"Not a stable published release: {repo}: {tag!r}")
    # Validate before using an upstream tag as a refspec; never interpolate into shell.
    run("git", "check-ref-format", f"refs/tags/{tag}")
    git(root, "fetch", "--no-tags", f"https://github.com/{repo}.git",
        f"refs/tags/{tag}:refs/i18n/{namespace}/{tag}")
    sha = git(root, "rev-parse", f"refs/i18n/{namespace}/{tag}^{{commit}}")
    return {"tag": tag, "sha": sha, "release_id": data["id"], "url": data["html_url"]}


def previous_sha(root, state, repo, namespace, prefix):
    tag = state.get(prefix + "_release")
    if not tag:
        raise RuntimeError(f"Missing baseline: {prefix}_release; explicit review is required")
    run("git", "check-ref-format", f"refs/tags/{tag}")
    git(root, "fetch", "--no-tags", f"https://github.com/{repo}.git",
        f"refs/tags/{tag}:refs/i18n/previous-{namespace}/{tag}")
    resolved = git(root, "rev-parse", f"refs/i18n/previous-{namespace}/{tag}^{{commit}}")
    pinned = state.get(prefix + "_commit")
    if pinned and pinned != resolved:
        raise RuntimeError(f"Previously recorded tag moved: {repo} {tag}: {pinned} -> {resolved}")
    return resolved


def ancestor(root, old, new):
    result = run("git", "merge-base", "--is-ancestor", old, new, cwd=root, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    return result.returncode == 0


def merge_release(root, previous, latest):
    if not ancestor(root, previous, latest):
        raise RuntimeError("Customs release history diverged or regressed; merge blocked")
    if not ancestor(root, previous, "HEAD"):
        raise RuntimeError("Localization does not contain the recorded Customs baseline")
    if ancestor(root, latest, "HEAD"):
        return False
    result = run("git", "merge", "--no-ff", "--no-edit", latest, cwd=root, check=False)
    if result.returncode:
        conflicts = git(root, "diff", "--name-only", "--diff-filter=U")
        git(root, "merge", "--abort")
        raise RuntimeError(f"Customs merge conflict:\n{conflicts}\n{result.stderr}")
    return True


def preserve_pack(before, after):
    for key, value in before.get("strings", {}).items():
        if after.get("strings", {}).get(key) != value:
            raise RuntimeError(f"Existing Italian translation changed or lost: {key!r}")
    for key, value in before.get("dashboard_titles", {}).items():
        if after.get("dashboard_titles", {}).get(key) != value:
            raise RuntimeError(f"Existing Italian dashboard title changed or lost: {key!r}")
    if not set(before.get("passthrough", [])) <= set(after.get("passthrough", [])):
        raise RuntimeError("Existing passthrough entries lost")


def issue(repo, title, body):
    # Exact title matching over every page avoids search indexing delays and duplicates.
    pages = run("gh", "api", "--paginate", "--slurp",
                f"repos/{repo}/issues?state=open&per_page=100").stdout
    for page in json.loads(pages):
        for item in page:
            if item.get("title") == title and "pull_request" not in item:
                print(f"Existing issue: {item['html_url']}")
                return item["html_url"]
    return api(f"repos/{repo}/issues", {"title": title, "body": body[:60000]})["html_url"]


def publish(root, branch, expected):
    current = git(root, "ls-remote", "origin", f"refs/heads/{branch}").split()[0]
    if current != expected:
        raise RuntimeError(f"Concurrent branch update: expected {expected}, found {current}; push blocked")
    # Never rebase, reset a remote ref, or use a force/lease push.
    git(root, "push", "origin", f"HEAD:refs/heads/{branch}")


def synchronize(args):
    root = Path(args.root).resolve()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = {"status": "checking", "branch": args.branch, "runtime": "not run"}
    stage = "resolve releases"
    try:
        start = git(root, "rev-parse", "HEAD")
        report["starting_commit"] = start
        customs = release(root, CUSTOMS, "customs")
        teslamate = release(root, TESLAMATE, "teslamate")
        report.update(customs=customs, teslamate=teslamate)
        state = json.loads((root / STATE).read_text())
        custom_old = previous_sha(root, state, CUSTOMS, "customs", "custom_dashboards")
        tm_old = previous_sha(root, state, TESLAMATE, "teslamate", "teslamate")
        if not ancestor(root, tm_old, teslamate["sha"]):
            raise RuntimeError("TeslaMate release history diverged or regressed")
        changed = git(root, "diff", "--name-only", tm_old, teslamate["sha"]).splitlines()
        sensitive = [path for path in changed if SENSITIVE.search(path)]
        report["teslamate_changed_files"] = changed
        report["compatibility_sensitive_files"] = sensitive
        if sensitive:
            report["compatibility_diff"] = git(root, "diff", "--stat", tm_old, teslamate["sha"])
            # Retain actual changes for review, not just filenames.
            (out / "teslamate-sensitive.diff").write_text(
                git(root, "diff", tm_old, teslamate["sha"], "--", *sensitive) + "\n")
        before = json.loads((root / "i18n/it.json").read_text())
        with tempfile.TemporaryDirectory(prefix="i18n-sync-") as tmp:
            work = Path(tmp) / "candidate"
            git(root, "worktree", "add", "--detach", str(work), start)
            try:
                git(work, "config", "user.name", "github-actions[bot]")
                git(work, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
                stage = "merge Customs release"
                report["merged"] = merge_release(work, custom_old, customs["sha"])
                preserve_pack(before, json.loads((work / "i18n/it.json").read_text()))
                stage = "validate and generate Italian dashboards"
                run(sys.executable, "scripts/validate_dashboards.py", "--no-sql", cwd=work)
                run(sys.executable, "scripts/validate_localization.py", cwd=work)
                run(sys.executable, "scripts/generate_localized_dashboards.py", "--output",
                    str(out / "dashboards"), cwd=work)
                paths = sorted((out / "dashboards").glob("*.json"))
                if len(paths) != len(list((work / "dashboards").glob("*.json"))) or not paths:
                    raise RuntimeError("Generated dashboard count mismatch")
                report["generated_dashboards"] = len(paths)
                provisioning = out / "provisioning/datasources"
                provisioning.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(work / "i18n/teslamate-datasource.yml", provisioning / "datasource.yml")
                stage = "runtime SQL and Grafana compatibility"
                if not args.runtime:
                    if args.push:
                        raise RuntimeError("Publishing requires --runtime; static checks alone are insufficient")
                    report["runtime"] = "skipped (read-only local validation)"
                else:
                    runtime_script = Path(__file__).with_name("check_teslamate_runtime.py")
                    run(sys.executable, str(runtime_script), "--root", str(work),
                        "--generated", str(out / "dashboards"), "--release", teslamate["tag"],
                        "--report-dir", str(out), timeout=1500)
                    report["runtime"] = "SQL and Grafana provisioning passed"
                # A sensitive diff requires a visible review record even after smoke tests pass.
                if sensitive and args.push:
                    stage = "create compatibility review issue"
                    report["review_issue"] = issue(os.environ["GITHUB_REPOSITORY"],
                        f"Italian localization: review TeslaMate {teslamate['tag']}",
                        f"Release: {teslamate['url']}\nCompare: https://github.com/{TESLAMATE}/compare/"
                        f"{state['teslamate_release']}...{teslamate['tag']}\n\n"
                        f"{report['runtime']}. Smoke tests do not cover every data value or browser panel.\n\n"
                        "Sensitive changes:\n" + "\n".join(f"- `{p}`" for p in sensitive) +
                        f"\n\nRun and diff artifact: {run_url()}\n")
                new_state = dict(state)
                for prefix, value in (("custom_dashboards", customs), ("teslamate", teslamate)):
                    new_state.update({prefix + "_release": value["tag"],
                                      prefix + "_commit": value["sha"],
                                      prefix + "_release_id": value["release_id"]})
                new_state["compatibility_validation"] = report["runtime"]
                if args.push:
                    (work / STATE).write_text(json.dumps(new_state, indent=2) + "\n")
                    git(work, "add", STATE)
                    if run("git", "diff", "--cached", "--quiet", cwd=work, check=False).returncode:
                        git(work, "commit", "-m", "chore(i18n): record validated upstream releases and commits")
                    stage = "publish validated candidate"
                    publish(work, args.branch, start)
                report["candidate_commit"] = git(work, "rev-parse", "HEAD")
                report["status"] = "passed" if args.push else "dry-run passed"
            finally:
                git(root, "worktree", "remove", "--force", str(work))
    except Exception as exc:
        report.update(status="failed", failed_stage=stage, error=str(exc)[-30000:])
        if stage == "runtime SQL and Grafana compatibility":
            report["runtime"] = "failed (see runtime and SQL logs)"
        print(f"ERROR: {stage}: {exc}", file=sys.stderr)
        if args.push:
            try:
                key = hashlib.sha256((stage + json.dumps(report.get("customs", {}), sort_keys=True) +
                                     json.dumps(report.get("teslamate", {}), sort_keys=True)).encode()).hexdigest()[:12]
                report["failure_issue"] = issue(os.environ["GITHUB_REPOSITORY"],
                    f"Italian localization sync blocked: {stage} [{key}]",
                    f"Stage: {stage}\nRun: {run_url()}\n\nThe candidate was not published.\n\n"
                    "```json\n" + json.dumps(report, ensure_ascii=False, indent=2)[-50000:] + "\n```\n"
                    "Resolve the conflict, missing translation, runtime failure or baseline issue, then rerun. "
                    "See the run artifacts for generated files and the TeslaMate sensitive diff.")
            except Exception as issue_error:
                report["issue_error"] = str(issue_error)
                print(f"::error::Could not create failure issue: {issue_error}")
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    summary = (f"## Italian localization sync\n\nStatus: **{report['status']}**\n\n"
               f"- Customs: {report.get('customs', {}).get('tag', 'unresolved')}\n"
               f"- TeslaMate: {report.get('teslamate', {}).get('tag', 'unresolved')}\n"
               f"- Generated dashboards: {report.get('generated_dashboards', 0)}\n"
               f"- Runtime: {report['runtime']}\n"
               f"- Details: report.json and logs in the run artifacts\n")
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as handle:
            handle.write(summary)
    return 1 if report["status"] == "failed" else 0


def run_url():
    return (f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/"
            f"{os.environ.get('GITHUB_RUN_ID', '')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", required=True)
    parser.add_argument("--branch", default=BRANCH)
    parser.add_argument("--runtime", action="store_true")
    parser.add_argument("--push", action="store_true")
    raise SystemExit(synchronize(parser.parse_args()))
