# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

provider "aws" {
  region = "us-east-2"
}

resource "aws_sqs_queue" "test_sqs" {
  name = uuid()
}

resource "aws_sqs_queue_policy" "test_sqs_policy" {
  queue_url = aws_sqs_queue.test_sqs.id

  policy = <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SpecificAllow",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::644160558196:root"
      },
      "Action": [
        "sqs:Subscribe"
      ]
    },
    {
      "Sid": "Public",
      "Effect": "Allow",
      "Principal": "*",
      "Action": [
        "sqs:GetqueueAttributes"
      ]
    }
  ]
}
POLICY
}
