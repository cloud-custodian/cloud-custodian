# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

provider "aws" {
  region = "us-west-2"
}

resource "aws_datapipeline_pipeline" "test_pipeline" {
  name = uuid()
}
