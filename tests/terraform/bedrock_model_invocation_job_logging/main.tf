provider "aws" {}

resource "aws_s3_bucket" "input" {
  bucket        = "c7n-bedrock-input-${terraform.workspace}"
  force_destroy = true
}

resource "aws_s3_bucket" "output" {
  bucket        = "c7n-bedrock-output-${terraform.workspace}"
  force_destroy = true
}

resource "aws_s3_bucket" "logging" {
  bucket        = "c7n-bedrock-model-invocation-logging-${terraform.workspace}"
  force_destroy = true
}

resource "aws_s3_object" "input" {
  bucket  = aws_s3_bucket.input.id
  key     = "input.jsonl"
  content = <<EOT
{"recordId":"1","modelInput":{"inputText":"Hello from c7n"}}
EOT
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "bedrock_batch" {
  name               = "c7n-bedrock-batch-${terraform.workspace}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

data "aws_iam_policy_document" "batch_access" {
  statement {
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.input.arn,
      "${aws_s3_bucket.input.arn}/*",
    ]
  }

  statement {
    actions = [
      "s3:AbortMultipartUpload",
      "s3:ListBucket",
      "s3:PutObject",
    ]
    resources = [
      aws_s3_bucket.output.arn,
      "${aws_s3_bucket.output.arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "bedrock_batch" {
  name   = "c7n-bedrock-batch-${terraform.workspace}"
  role   = aws_iam_role.bedrock_batch.id
  policy = data.aws_iam_policy_document.batch_access.json
}

resource "aws_bedrock_model_invocation_logging_configuration" "enabled" {
  logging_config {
    text_data_delivery_enabled      = true
    image_data_delivery_enabled     = false
    embedding_data_delivery_enabled = false

    s3_config {
      bucket_name = aws_s3_bucket.logging.id
      key_prefix  = "bedrock/model-invocation-logging/"
    }
  }
}

output "input_s3_uri" {
  value = "s3://${aws_s3_bucket.input.bucket}/${aws_s3_object.input.key}"
}

output "output_s3_uri" {
  value = "s3://${aws_s3_bucket.output.bucket}/"
}
