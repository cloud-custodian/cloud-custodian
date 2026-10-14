provider "aws" {}

resource "aws_dx_gateway" "test_gateway" {
  name            = "c7n-test-directconnect-tagging"
  amazon_side_asn = 64512

  tags = {
    existing = "existing"
  }
}

