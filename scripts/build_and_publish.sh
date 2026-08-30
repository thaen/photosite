#!/usr/bin/env bash
# Build the site, append changed deployable targets to a durable upload queue,
# then publish queued files. No deletion is allowed.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
pending_list=${PHOTOSITE_UPLOAD_LIST:-"$root/work/pending-s3-upload-list.txt"}
bucket=${PHOTOSITE_S3_BUCKET:-efj-site-east-1}
profile=${PHOTOSITE_AWS_PROFILE:-piathome}
aws=${PHOTOSITE_AWS:-/usr/local/bin/aws}

cd "$root"
mkdir -p "$(dirname "$pending_list")"
touch "$pending_list"

PHOTOSITE_UPLOAD_LIST="$pending_list" \
    .venv/bin/doit run -n "${PHOTOSITE_DOIT_PROCESSES:-4}"

if [[ ! -s "$pending_list" ]]; then
    printf 'The upload queue is empty.\n'
    exit 0
fi

upload_args=(--list "$pending_list" --bucket "$bucket" --profile "$profile" --aws "$aws")
if [[ ${PHOTOSITE_RELEASE_DRY_RUN:-0} == 1 ]]; then
    python3 scripts/upload_doit_targets.py "${upload_args[@]}" --dry-run
    exit 0
fi

python3 scripts/upload_doit_targets.py "${upload_args[@]}"
if [[ ! -s "$pending_list" ]]; then
    printf 'The upload queue is complete.\n'
else
    printf 'The upload queue still has queued files.\n'
fi
