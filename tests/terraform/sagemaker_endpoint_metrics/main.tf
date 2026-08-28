provider "aws" {}

resource "random_pet" "main" {
  length    = 2
  separator = "-"
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "c7n-endpoint-metrics-${random_pet.main.id}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"
}

resource "aws_s3_bucket" "model" {
  bucket        = "c7n-sagemaker-endpoint-metrics-${random_pet.main.id}"
  force_destroy = true
}

# see README.md for how model.tar.gz is built
resource "aws_s3_object" "model" {
  bucket = aws_s3_bucket.model.id
  key    = "model.tar.gz"
  source = "${path.module}/model.tar.gz"
  etag   = filemd5("${path.module}/model.tar.gz")
}

data "aws_sagemaker_prebuilt_ecr_image" "xgboost" {
  repository_name = "sagemaker-xgboost"
  image_tag       = "1.7-1"
}

resource "aws_sagemaker_model" "main" {
  name               = "c7n-endpoint-metrics-${random_pet.main.id}"
  execution_role_arn = aws_iam_role.execution.arn

  primary_container {
    image          = data.aws_sagemaker_prebuilt_ecr_image.xgboost.registry_path
    model_data_url = "s3://${aws_s3_bucket.model.id}/${aws_s3_object.model.key}"
  }
}

# Only the second variant is invoked, so an idle-endpoint policy must skip
# this endpoint -- which it can only do by querying every variant.
resource "aws_sagemaker_endpoint_configuration" "busy" {
  name = "c7n-endpoint-metrics-busy-${random_pet.main.id}"

  production_variants {
    variant_name           = "quiet"
    model_name             = aws_sagemaker_model.main.name
    initial_instance_count = 1
    instance_type          = "ml.t2.medium"
    initial_variant_weight = 1
  }

  production_variants {
    variant_name           = "busy"
    model_name             = aws_sagemaker_model.main.name
    initial_instance_count = 1
    instance_type          = "ml.t2.medium"
    initial_variant_weight = 1
  }
}

resource "aws_sagemaker_endpoint_configuration" "idle" {
  name = "c7n-endpoint-metrics-idle-${random_pet.main.id}"

  production_variants {
    variant_name           = "AllTraffic"
    model_name             = aws_sagemaker_model.main.name
    initial_instance_count = 1
    instance_type          = "ml.t2.medium"
    initial_variant_weight = 1
  }
}

resource "aws_sagemaker_endpoint" "busy" {
  name                 = "c7n-endpoint-metrics-busy-${random_pet.main.id}"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.busy.name
}

resource "aws_sagemaker_endpoint" "idle" {
  name                 = "c7n-endpoint-metrics-idle-${random_pet.main.id}"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.idle.name
}
