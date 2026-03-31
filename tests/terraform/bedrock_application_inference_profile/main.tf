# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

provider "aws" {}

# Create an application inference profile
resource "aws_bedrock_inference_profile" "test_profile" {
  name        = "c7n-test-profile-${substr(uuid(), 0, 8)}"
  description = "Test profile for C7N"

  model_source {
    copy_from = "arn:aws:bedrock:us-east-1::inference-profile/global.amazon.nova-2-lite-v1:0"
  }

  tags = {
    Environment = "test"
    Owner       = "c7n"
  }
}
