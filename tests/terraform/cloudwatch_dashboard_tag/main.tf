# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
provider "aws" {}

resource "random_id" "id" {
  byte_length = 8
}

resource "aws_cloudwatch_dashboard" "test" {
  dashboard_name = "c7n-test-${random_id.id.hex}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 6
        height = 6
        properties = {
          markdown = "cloud custodian test dashboard"
        }
      }
    ]
  })
}
