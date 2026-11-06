# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

provider "aws" {
  region = "us-east-1"
}

data "aws_caller_identity" "current" {}

resource "random_id" "suffix" {
  byte_length = 2
}

locals {
  job_name  = "c7n-evaluation-${terraform.workspace}-${random_id.suffix.hex}"
  model_arn = "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0"
}

resource "aws_s3_bucket" "output" {
  bucket        = "${local.job_name}-output"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "output" {
  bucket = aws_s3_bucket.output.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "output" {
  bucket = aws_s3_bucket.output.id

  depends_on = [aws_s3_bucket_versioning.output]

  rule {
    id     = "evaluation-output-retention"
    status = "Enabled"

    filter {
      prefix = "evaluations/"
    }

    expiration {
      days = 30
    }

    noncurrent_version_expiration {
      noncurrent_days = 10
    }
  }
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values = [
        "arn:aws:bedrock:us-east-1:${data.aws_caller_identity.current.account_id}:evaluation-job/*"
      ]
    }
  }
}

resource "aws_iam_role" "bedrock_evaluation" {
  name               = "${local.job_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

data "aws_iam_policy_document" "bedrock_evaluation" {
  statement {
    actions = [
      "s3:AbortMultipartUpload",
      "s3:GetBucketLocation",
      "s3:GetObject",
      "s3:ListBucket",
      "s3:PutObject",
    ]
    resources = [
      aws_s3_bucket.output.arn,
      "${aws_s3_bucket.output.arn}/*",
    ]
  }

  statement {
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = [local.model_arn]
  }

  statement {
    actions = [
      "bedrock:CreateModelInvocationJob",
      "bedrock:GetInferenceProfile",
      "bedrock:GetModelInvocationJob",
      "bedrock:GetProvisionedModelThroughput",
      "bedrock:StopModelInvocationJob",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "bedrock_evaluation" {
  name   = local.job_name
  role   = aws_iam_role.bedrock_evaluation.id
  policy = data.aws_iam_policy_document.bedrock_evaluation.json
}

output "job_name" {
  value = local.job_name
}

output "model_arn" {
  value = local.model_arn
}

output "output_s3_uri" {
  value = "s3://${aws_s3_bucket.output.bucket}/evaluations/"
}

output "role_arn" {
  value = aws_iam_role.bedrock_evaluation.arn
}
