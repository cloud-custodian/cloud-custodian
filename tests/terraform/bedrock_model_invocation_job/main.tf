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

  statement {
    actions = [
      "bedrock:InvokeModel",
    ]
    resources = [
      "arn:aws:bedrock:*::foundation-model/*",
    ]
  }
}

resource "aws_iam_role_policy" "bedrock_batch" {
  name   = "c7n-bedrock-batch-${random_pet.job.id}"
  role   = aws_iam_role.bedrock_batch.id
  policy = data.aws_iam_policy_document.batch_access.json
}

# Output the resources needed to create the job via helper method
output "role_arn" {
  value = aws_iam_role.bedrock_batch.arn
}

output "input_bucket" {
  value = aws_s3_bucket.input.bucket
}

output "output_bucket" {
  value = aws_s3_bucket.output.bucket
}

output "input_s3_uri" {
  value = "s3://${aws_s3_bucket.input.bucket}/${aws_s3_object.input.key}"
}

output "output_s3_uri" {
  value = "s3://${aws_s3_bucket.output.bucket}/"
}

output "job_name_prefix" {
  value = "c7n-batch-invocation-${random_pet.job.id}"
}
