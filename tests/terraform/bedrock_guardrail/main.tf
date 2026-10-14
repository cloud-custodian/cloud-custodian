# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

provider "aws" {}

# Create an application inference profile
resource "aws_bedrock_guardrail" "test_guardrail" {
  name                      = "c7n-test-guardrail-${substr(uuid(), 0, 8)}"
  description               = "Test guardrail for C7N"
  blocked_input_messaging   = "example"
  blocked_outputs_messaging = "example"

  content_policy_config {
    filters_config {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
      type            = "HATE"
    }
    tier_config {
      tier_name = "CLASSIC"
    }
  }


  tags = {
    Environment = "test"
    Owner       = "c7n"
  }
}
