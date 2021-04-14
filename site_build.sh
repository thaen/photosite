#!/bin/bash

SOURCE_BUCKET=efj-originals-east-1
TARGET_BUCKET=efj-site-east-1

BUILD_DIR=site
CONTENT_DIR=content

set -euxo pipefail

cd ~/photosite/
git pull --rebase

pushd ${CONTENT_DIR}
# TODO: to add --delete here we have to move the orderfiles to a place outside the content/ dir
aws s3 sync s3://${SOURCE_BUCKET}/ .
popd

doit -n 4

pushd ${BUILD_DIR}
aws s3 sync --delete . s3://${TARGET_BUCKET}/
popd
