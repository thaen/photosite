#!/usr/bin/env python3
"""Upload the queued deployable paths that successful builds recorded."""

import argparse
import email.utils
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class Entry:
    def __init__(self, raw, key, mtime_ns=None, size=None):
        self.raw = raw
        self.key = key
        self.mtime_ns = mtime_ns
        self.size = size


def parse_entry(line):
    parts = line.rstrip("\n").split("\t")
    key = parts[0]
    mtime_ns = int(parts[1]) if len(parts) > 1 and parts[1] else None
    size = int(parts[2]) if len(parts) > 2 and parts[2] else None
    return Entry(line, key, mtime_ns, size)


def queue_line(key, source):
    st = source.stat()
    return f"{key}\t{st.st_mtime_ns}\t{st.st_size}\n"


def run_aws(args, aws, profile):
    return subprocess.run([aws, "--profile", profile, *args], check=True, text=True, capture_output=True)


def remote_is_current(args, entry, source):
    if entry.mtime_ns is None or entry.size is None:
        return False
    try:
        result = run_aws([
            "s3api", "head-object", "--bucket", args.bucket, "--key", entry.key,
            "--query", "{LastModified:LastModified,ContentLength:ContentLength}", "--output", "json",
        ], args.aws, args.profile)
    except subprocess.CalledProcessError:
        return False
    import json
    data = json.loads(result.stdout)
    if int(data["ContentLength"]) != source.stat().st_size:
        return False
    remote_dt = email.utils.parsedate_to_datetime(data["LastModified"])
    if remote_dt.tzinfo is None:
        remote_dt = remote_dt.replace(tzinfo=timezone.utc)
    queued_dt = datetime.fromtimestamp(entry.mtime_ns / 1_000_000_000, timezone.utc)
    return remote_dt >= queued_dt


def validate_source(site, key):
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
        for entry in entries:
            tmp.write(entry.raw if entry.raw.endswith("\n") else entry.raw + "\n")
    Path(tmp_name).replace(path)


def upload(args):
    site = Path(args.site).resolve()
    queue = Path(args.list)
    raw_lines = queue.read_text(encoding="utf-8").splitlines(True) if queue.exists() else []
    entries = [parse_entry(line) for line in raw_lines if line.strip()]
    remaining = []
    uploaded = 0
    skipped = 0
    for entry in entries:
        source = validate_source(site, entry.key)
        if args.dry_run:
            print(f"{args.aws} --profile {args.profile} s3 cp --only-show-errors {source} s3://{args.bucket}/{entry.key}")
            remaining.append(entry)
            continue
        if remote_is_current(args, entry, source):
            skipped += 1
            continue
        command = [args.aws, "--profile", args.profile, "s3", "cp", "--only-show-errors", str(source), f"s3://{args.bucket}/{entry.key}"]
        try:
            subprocess.run(command, check=True)
            uploaded += 1
        except subprocess.CalledProcessError:
            remaining.append(entry)
    if not args.dry_run:
        rewrite_queue(queue, remaining)
        print(f"Uploaded {uploaded} files. Skipped {skipped} current files. {len(remaining)} queued files remain.")
    else:
        print(f"Would process {len(entries)} queued files.")


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
        upload(args)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
