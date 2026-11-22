#!/usr/bin/env python3
"""Upload the queued deployable paths that successful builds recorded."""

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


def validate_source(site, key):
    site = site.resolve()
    source = (site / key).resolve()
    if source.parent != site and site not in source.parents:
        raise RuntimeError(f"Upload path escapes site/: {key}")
    if not source.is_file() or source.name == ".DS_Store":
        raise RuntimeError(f"Recorded output is not deployable: {key}")
    return source


def rewrite_queue(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as tmp:
        for raw in entries:
            tmp.write(raw if raw.endswith("\n") else raw + "\n")
        tmp.flush()
        os.fsync(tmp.fileno())
    Path(tmp_name).replace(path)


def upload(args):
    site = Path(args.site).resolve()
    queue = Path(args.list)
    raw_lines = queue.read_text(encoding="utf-8").splitlines(True) if queue.exists() else []
    entries = {line.rstrip("\n").split("\t", 1)[0]: line for line in raw_lines if line.strip()}
    remaining = []
    uploaded = 0
    for key, raw in entries.items():
        source = validate_source(site, key)
        if args.dry_run:
            print(f"{args.aws} --profile {args.profile} s3 cp --only-show-errors {source} s3://{args.bucket}/{key}")
            remaining.append(raw)
            continue
        command = [args.aws, "--profile", args.profile, "s3", "cp", "--only-show-errors", str(source), f"s3://{args.bucket}/{key}"]
        try:
            subprocess.run(command, check=True)
            uploaded += 1
        except subprocess.CalledProcessError:
            remaining.append(raw)
    if not args.dry_run:
        rewrite_queue(queue, remaining)
        print(f"Uploaded {uploaded} files. {len(remaining)} queued files remain.")
    else:
        print(f"Would process {len(entries)} queued files.")
    return 0 if args.dry_run or not remaining else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", required=True)
    parser.add_argument("--site", default="site")
    parser.add_argument("--bucket", default="efj-site-east-1")
    parser.add_argument("--profile", default="piathome")
    parser.add_argument("--aws", default="/usr/local/bin/aws")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        return upload(args)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
