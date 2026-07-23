# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

provider "aws" {
  region = "us-east-1"
}

data "aws_caller_identity" "current" {}

resource "random_id" "suffix" {
  byte_length = 2
}

resource "aws_bedrock_inference_profile" "token_metrics" {
  name        = "c7n-token-metrics-${terraform.workspace}-${random_id.suffix.hex}"
  description = "Cloud Custodian combined token metrics test"

  model_source {
    copy_from = "arn:aws:bedrock:us-east-1:${data.aws_caller_identity.current.account_id}:inference-profile/us.amazon.nova-lite-v1:0"
  }
}

output "inference_profile_arn" {
  value = aws_bedrock_inference_profile.token_metrics.arn
}
