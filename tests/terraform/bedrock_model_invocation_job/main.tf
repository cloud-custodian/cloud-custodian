provider "aws" {}

resource "random_pet" "job" {
  length    = 2
  separator = "-"
}

resource "aws_s3_bucket" "input" {
  bucket        = "c7n-bedrock-input-${random_pet.job.id}"
  force_destroy = true
}

resource "aws_s3_bucket" "output" {
  bucket        = "c7n-bedrock-output-${random_pet.job.id}"
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
  name               = "c7n-bedrock-batch-${random_pet.job.id}"
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
  name   = "c7n-bedrock-batch-${random_pet.job.id}"
  role   = aws_iam_role.bedrock_batch.id
  policy = data.aws_iam_policy_document.batch_access.json
}

resource "aws_bedrock_model_invocation_job" "test_job" {
  job_name = "c7n-batch-invocation-${random_pet.job.id}"
  model_id = "amazon.titan-text-express-v1"
  role_arn = aws_iam_role.bedrock_batch.arn

  input_data_config {
    s3_input_data_config {
      s3_uri = "s3://${aws_s3_bucket.input.bucket}/${aws_s3_object.input.key}"
    }
  }

  output_data_config {
    s3_output_data_config {
      s3_uri = "s3://${aws_s3_bucket.output.bucket}/"
    }
  }

  tags = {
    Owner = "c7n"
  }
}
