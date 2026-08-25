#!/usr/bin/env python3
"""Upload the deployable paths that a successful doit build recorded."""

import argparse
import subprocess
from pathlib import Path


def upload(args):
    site = Path(args.site).resolve()
    listed = Path(args.list).read_text(encoding="utf-8").splitlines()
    keys = sorted(set(key for key in listed if key))
    for key in keys:
        source = (site / key).resolve()
        if source.parent != site and site not in source.parents:
            raise RuntimeError(f"Upload path escapes site/: {key}")
        if not source.is_file() or source.name == ".DS_Store":
            raise RuntimeError(f"Recorded output is not deployable: {key}")
        command = [args.aws, "--profile", args.profile, "s3", "cp",
                   "--only-show-errors", str(source),
                   f"s3://{args.bucket}/{key}"]
        if args.dry_run:
            print(" ".join(command))
        else:
            subprocess.run(command, check=True)
    print(f"Uploaded {len(keys)} files." if not args.dry_run
          else f"Would upload {len(keys)} files.")


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
