provider "aws" {}

resource "random_pet" "main" {
  length    = 2
  separator = "-"
}

locals {
  # jobs have to run long enough to report a minute of utilization metrics.
  # range() tops out at 1024, hence the repeated blocks.
  train_block = join("\n", [
    for i in range(1000) : format("%d,%f", i % 2, (i % 97) / 97.0)
  ])
  train_csv = join("\n", [for i in range(50) : local.train_block])

  transform_block = join("\n", [
    for i in range(1000) : format("%f", (i % 97) / 97.0)
  ])
  transform_csv = join("\n", [for i in range(200) : local.transform_block])
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
  name               = "c7n-job-metrics-${random_pet.main.id}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"
}

resource "aws_s3_bucket" "data" {
  bucket        = "c7n-sagemaker-job-metrics-${random_pet.main.id}"
  force_destroy = true
}

resource "aws_s3_object" "train" {
  bucket  = aws_s3_bucket.data.id
  key     = "train/train.csv"
  content = local.train_csv
}

resource "aws_s3_object" "transform" {
  bucket  = aws_s3_bucket.data.id
  key     = "transform/transform.csv"
  content = local.transform_csv
}

# see ../sagemaker_endpoint_metrics/README.md for how model.tar.gz is built
resource "aws_s3_object" "model" {
  bucket = aws_s3_bucket.data.id
  key    = "model.tar.gz"
  source = "${path.module}/model.tar.gz"
  etag   = filemd5("${path.module}/model.tar.gz")
}

data "aws_sagemaker_prebuilt_ecr_image" "xgboost" {
  repository_name = "sagemaker-xgboost"
  image_tag       = "1.7-1"
}

resource "aws_sagemaker_model" "main" {
  name               = "c7n-job-metrics-${random_pet.main.id}"
  execution_role_arn = aws_iam_role.execution.arn

  primary_container {
    image          = data.aws_sagemaker_prebuilt_ecr_image.xgboost.registry_path
    model_data_url = "s3://${aws_s3_bucket.data.id}/${aws_s3_object.model.key}"
  }
}

output "role_arn" {
  value = aws_iam_role.execution.arn
}

output "image_uri" {
  value = data.aws_sagemaker_prebuilt_ecr_image.xgboost.registry_path
}

output "model_name" {
  value = aws_sagemaker_model.main.name
}

output "job_name" {
  value = "c7n-job-metrics-${random_pet.main.id}"
}

output "train_s3_uri" {
  value = "s3://${aws_s3_bucket.data.id}/train/"
}

output "transform_s3_uri" {
  value = "s3://${aws_s3_bucket.data.id}/transform/"
}

output "output_s3_uri" {
  value = "s3://${aws_s3_bucket.data.id}/output/"
}
