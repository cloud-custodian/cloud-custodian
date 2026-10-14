# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

provider "aws" {
  region = "us-east-2"
}

data "aws_caller_identity" "current" {}

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
        "AWS": "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
      },
      "Resource": "${aws_sqs_queue.test_sqs.arn}",
      "Action": [
        "sqs:SetQueueAttributes"
      ]
    },
    {
      "Sid": "Public",
      "Effect": "Allow",
      "Principal": "*",
      "Resource": "${aws_sqs_queue.test_sqs.arn}",
      "Action": [
        "sqs:GetqueueAttributes"
      ]
    }
  ]
}
POLICY
}
