#!/bin/bash

# The goal of this script is to download new photos from the "source" s3 bucket
# and avoid running S3 operations unless they must be run.
#
# This script (actually the whole repo) is pulled down regularly to a host.
#
# There is an S3 bcuket (call it "source") that I can upload to from
#  my phone (or laptop, w/e). That bucket is configured so that when
#  somethig uploads to it, a SQS message is generated. The message
#  itself is unimportant, but it tells us there's new content.
#
# So, when there's such a message, the build host syncs from the
# bucket, runs this script, and uplaods the resulting target
# bucket. Which usually doesn't change much, so there's not much for
# s3 sync to do.


export AWS_DEFAULT_REGION=us-east-1

SOURCE_BUCKET=efj-originals-east-1
TARGET_BUCKET=efj-site-east-1

BUILD_DIR=site
CONTENT_DIR=content

set -euxo pipefail

cd ~/photosite/
git pull --rebase

QUEUE_URL=$(aws cloudformation describe-stacks --stack-name bucket --query 'Stacks[0].Outputs[?OutputKey==`QueueURL`].OutputValue' --output text)

if aws sqs receive-message --queue-url ${QUEUE_URL} | grep MessageId; then
    # There's a message, meaning a new image! We want to run stuff.
    # First, we purge. We could purge after too, but that would result
    # in lots and lots of S3 operations if there's a systemic failure.
    aws sqs purge-queue --queue-url ${QUEUE_URL}
else
    exit 0
fi

pushd ${CONTENT_DIR}
# TODO: to add --delete here we have to move the orderfiles to a place outside the content/ dir
aws s3 sync s3://${SOURCE_BUCKET}/ .
popd

doit -n 4

pushd ${BUILD_DIR}
aws s3 sync --delete . s3://${TARGET_BUCKET}/
popd
