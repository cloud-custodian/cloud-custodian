# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

provider "aws" {
  region = "us-west-2"
}

resource "aws_sqs_queue" "test_sqs" {
  name = uuid()
}

resource "aws_kms_key" "test_key" {}

resource "aws_kms_alias" "test_key_alias" {
  name          = join("/", ["alias", uuid()])
  target_key_id = aws_kms_key.test_key.key_id
}
