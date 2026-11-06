# Resources needed to create a custom model: buckets, training data, and an
# execution role. Terraform gives us less Python code and easy cleanup once the
# model exists. The model itself isn't defined here, because it needs to
# persist; ./setup.py submits the job that creates it.
#
# Applied by hand, not by a test. See README.md.

provider "aws" {
  region = local.region
}

locals {
  region = "us-west-2"

  # Fixed, not random: tests find the model by name, so a rebuild needs no test
  # edit. KEEP- warns off manual cleanup -- see README.md.
  custom_model_name = "KEEP-c7n-deployable-test-fixture"

  # Jobs can't be deleted, only stopped, so they pile up -- the username says
  # whose they are. setup.py appends a timestamp.
  job_name_prefix = "c7n-jimfulton-deployable-test-fixture"

  # Minimal required for fine tuning.
  hyperparameters = {
    epochCount   = "1"
    batchSize    = "1"
    learningRate = "0.00005"
  }

  # Not swappable: only a few base models support on-demand deployment, which
  # is what the deployments filter needs. See README.md.
  base_model_identifier = "arn:aws:bedrock:us-west-2::foundation-model/meta.llama3-3-70b-instruct-v1:0:128k"

  fixture_tags = {
    KEEP    = "jimfulton deployable test custom model"
    owner   = "jim.fulton@sixfeetup.com"
    purpose = "cloud-custodian issue 10984 test fixture"
  }
}

resource "random_pet" "fixture" {
  length    = 2
  separator = "-"
}

resource "aws_s3_bucket" "training" {
  bucket        = "c7n-bedrock-deployable-${random_pet.fixture.id}"
  force_destroy = true
}

resource "aws_s3_object" "training_data" {
  bucket = aws_s3_bucket.training.id
  key    = "train.jsonl"
  source = "${path.module}/train.jsonl"
  etag   = filemd5("${path.module}/train.jsonl")
}

resource "aws_s3_bucket" "output" {
  bucket        = "c7n-bedrock-deployable-output-${random_pet.fixture.id}"
  force_destroy = true
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

resource "aws_iam_role" "customization" {
  name               = "c7n-bedrock-deployable-${random_pet.fixture.id}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

data "aws_iam_policy_document" "customization_access" {
  statement {
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.training.arn, "${aws_s3_bucket.training.arn}/*"]
  }
  statement {
    actions   = ["s3:PutObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.output.arn, "${aws_s3_bucket.output.arn}/*"]
  }
}

resource "aws_iam_role_policy" "customization" {
  name   = "c7n-bedrock-deployable-${random_pet.fixture.id}"
  role   = aws_iam_role.customization.id
  policy = data.aws_iam_policy_document.customization_access.json
}

# Consumed by ./setup.py via `tofu output -json`.

output "region" {
  value = local.region
}

output "custom_model_name" {
  value = local.custom_model_name
}

output "job_name_prefix" {
  value = local.job_name_prefix
}

output "hyperparameters" {
  value = local.hyperparameters
}

output "base_model_identifier" {
  value = local.base_model_identifier
}

output "fixture_tags" {
  value = local.fixture_tags
}

output "training_data_s3_uri" {
  value = "s3://${aws_s3_bucket.training.id}/${aws_s3_object.training_data.key}"
}

output "output_s3_uri" {
  value = "s3://${aws_s3_bucket.output.id}/output/"
}

output "execution_role_arn" {
  value = aws_iam_role.customization.arn
}
