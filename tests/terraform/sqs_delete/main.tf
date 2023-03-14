# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

provider "aws" {
  region = "us-east-2"
}

resource "aws_sqs_queue" "test_sqs" {
  name = uuid()
}
