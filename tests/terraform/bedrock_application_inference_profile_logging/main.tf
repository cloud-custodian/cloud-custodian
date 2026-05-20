provider "aws" {}

resource "aws_s3_bucket" "logging" {
  bucket        = "c7n-bedrock-model-invocation-logging-${terraform.workspace}"
  force_destroy = true
}

resource "aws_bedrock_inference_profile" "test_profile" {
  name = "c7n-test-profile-${terraform.workspace}"

  model_source {
    copy_from = "arn:aws:bedrock:us-east-1::inference-profile/global.amazon.nova-2-lite-v1:0"
  }
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
