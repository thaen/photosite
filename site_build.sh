#!/bin/bash

SOURCE_BUCKET=efj-originals-east-1
TARGET_BUCKET=efj-site-east-1

BUILD_DIR=site
CONTENT_DIR=content

set -euxo pipefail

cd ~/photosite/
git pull --rebase
aws s3 sync s3://${SOURCE_BUCKET}/ ${CONTENT_DIR}
doit -n 4
pushd ${BUILD_DIR}
aws s3 sync . s3://${TARGET_BUCKET}/
popd
