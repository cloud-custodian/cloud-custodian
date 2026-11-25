# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
provider "aws" {
  region = "us-east-1"
}

resource "random_id" "id" {
  byte_length = 8
}

# An over-permissive customer managed policy. Action "*" is the case a
# name-based removal cannot reach, because "kms:Decrypt" appears nowhere in
# the document even though the policy allows it. Attached to no principal, so
# it grants nothing while the fixture exists.
resource "aws_iam_policy" "wildcard" {
  name = "c7n-test-deny-permissions-${random_id.id.hex}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AllowAll"
        Effect   = "Allow"
        Action   = "*"
        Resource = "*"
      }
    ]
  })
}
