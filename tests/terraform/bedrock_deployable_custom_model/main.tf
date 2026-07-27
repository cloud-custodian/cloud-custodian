# Prerequisites for building the "deployable" custom model test fixture.
#
# This module deliberately does NOT create the custom model. The
# aws_bedrock_custom_model resource *owns* the model -- its destroy deletes the
# model produced by the customization job -- but this model is a long-lived
# fixture that has to survive `tofu destroy` of these transient prerequisites.
# So Terraform creates only the buckets, training data, and IAM role, and
# ./setup.py submits the customization job. See README.md.
#
# NOTE: this module is applied manually, out of band. No test declares
# @terraform("bedrock_deployable_custom_model") -- the model must outlive any
# single test run. Do not wire it into a test.

provider "aws" {
  region = local.region
}

locals {
  region = "us-west-2"

  # Fixed and deliberately un-random: the tests select this fixture by
  # modelName, so rebuilding the model needs no test-code edit (only
  # re-recording). The KEEP- prefix is the signal to a human janitor, since
  # cleanup in this shared account is manual -- an earlier build of this model
  # was deleted by a colleague. Console list columns truncate near 17
  # characters, so the warning and the role come first ("KEEP-c7n-deployab...").
  custom_model_name = "KEEP-c7n-deployable-test-fixture"

  # Customization jobs can never be deleted (there is no
  # DeleteModelCustomizationJob API, only Stop), so they accumulate in the
  # account forever. Include the owner's GitHub username so whoever is cleaning
  # up later can attribute them. setup.py appends a timestamp for uniqueness.
  # No KEEP- prefix here: it would be meaningless on an undeletable resource.
  job_name_prefix = "c7n-jimfulton-deployable-test-fixture"

  # Required by CreateModelCustomizationJob for FINE_TUNING. Minimised: one
  # epoch over a tiny dataset, since only a valid completed model is needed,
  # not a good one. Values are strings (the API takes a string->string map).
  hyperparameters = {
    epochCount   = "1"
    batchSize    = "1"
    learningRate = "0.00005"
  }

  # Llama 3.3 70B Instruct is on the on-demand custom-model-deployment eligible
  # list in us-west-2, which is what the `deployments` filter's populated case
  # requires. (Nova models are also eligible, in us-east-1, but their
  # fine-tuning jobs do not complete in this account.) See
  # https://docs.aws.amazon.com/bedrock/latest/userguide/deploy-custom-model-on-demand.html
  base_model_identifier = "arn:aws:bedrock:us-west-2::foundation-model/meta.llama3-3-70b-instruct-v1:0:128k"

  # Applied to both the customization job and the resulting custom model by
  # setup.py (Terraform cannot tag a model it does not create). Tag values may
  # contain spaces; model names may not.
  fixture_tags = {
    KEEP    = "jimfulton deployable test custom model"
    owner   = "jim.fulton@sixfeetup.com"
    purpose = "cloud-custodian issue 10843 test fixture"
  }
}

# Only scopes bucket/role names. The prerequisites are rebuilt from scratch on
# every model rebuild, so a fresh value each time is fine and desirable.
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
