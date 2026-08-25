#!/usr/bin/env python3
"""Create and publish an explicit, no-delete static bootstrap release."""

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def run_aws(args, aws, profile):
    return subprocess.run(
        [aws, "--profile", profile, *args], check=True, text=True,
        capture_output=True,
    )


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def static_files(site, content_static):
    files = []
    for source in sorted(content_static.rglob("*")):
        if not source.is_file() or source.name == ".DS_Store":
            continue
        relative = source.relative_to(content_static)
        target = site / "static" / relative
        if not target.is_file():
            raise RuntimeError(f"Static build output is missing: {target}")
        files.append((target, (Path("static") / relative).as_posix()))
    favicon = site / "favicon.ico"
    if not favicon.is_file():
        raise RuntimeError(f"Favicon build output is missing: {favicon}")
    files.append((favicon, "favicon.ico"))
    return files


def make_plan(args):
    site = Path(args.site).resolve()
    content_static = Path(args.content_static).resolve()
    listed = json.loads(run_aws(
        ["s3api", "list-objects-v2", "--bucket", args.bucket, "--output", "json"],
        args.aws, args.profile,
    ).stdout).get("Contents", [])
    release_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    plan = {
        "schema": 1,
        "release_id": release_id,
        "mode": "static-bootstrap-no-delete",
        "bucket": args.bucket,
        "baseline": {
            "listed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "object_count": len(listed),
            "accepted_without_download": True,
        },
        "uploads": [
            {"key": key, "source": str(source), "bytes": source.stat().st_size,
             "sha256": sha256(source)}
            for source, key in static_files(site, content_static)
        ],
        "deletions": [],
    }
    plan["uploads"].sort(key=lambda item: item["key"])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {out}: {len(plan['uploads'])} uploads, 0 deletions.")


def publish(args):
    plan_path = Path(args.plan)
    plan = json.loads(plan_path.read_text())
    if plan.get("mode") != "static-bootstrap-no-delete" or plan.get("deletions"):
        raise RuntimeError("Refusing a plan that is not an explicit no-delete static bootstrap.")
    for entry in plan["uploads"]:
        source = Path(entry["source"])
        if not source.is_file() or sha256(source) != entry["sha256"]:
            raise RuntimeError(f"Source changed after planning: {source}")
        run_aws(["s3", "cp", "--only-show-errors", str(source),
                 f"s3://{plan['bucket']}/{entry['key']}"], args.aws, args.profile)
    release_key = f"_releases/releases/{plan['release_id']}.json"
    current_key = "_releases/current.json"
    run_aws(["s3", "cp", "--only-show-errors", str(plan_path),
             f"s3://{plan['bucket']}/{release_key}"], args.aws, args.profile)
    run_aws(["s3", "cp", "--only-show-errors", str(plan_path),
             f"s3://{plan['bucket']}/{current_key}"], args.aws, args.profile)
    print(f"Published {len(plan['uploads'])} static files and release manifest {release_key}.")


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--aws", default="aws")
    root.add_argument("--profile", default="piathome")
    sub = root.add_subparsers(required=True)
    plan = sub.add_parser("plan-static")
    plan.add_argument("--bucket", required=True)
    plan.add_argument("--site", default="site")
    plan.add_argument("--content-static", default="content/static")
    plan.add_argument("--out", required=True)
    plan.set_defaults(action=make_plan)
    publish = sub.add_parser("publish")
    publish.add_argument("--plan", required=True)
    publish.set_defaults(action=publish)
    return root


if __name__ == "__main__":
    try:
        args = parser().parse_args()
        args.action(args)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"release-manifest: {error}", file=sys.stderr)
        sys.exit(1)
