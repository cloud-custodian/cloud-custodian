resource "random_pet" "bucket" {
  prefix = "tf-test"
  length = 2
}


resource "random_pet" "group" {
  prefix    = "tf_testm"
  length    = 2
  separator = "_"
}

resource "aws_s3_bucket" "results" {
  bucket        = random_pet.bucket.id
  force_destroy = true
}


resource "aws_kms_key" "encrypt" {
  deletion_window_in_days = 7
  description             = "Athena Workgroup KMS Key"
}


resource "aws_athena_workgroup" "working" {
  name = random_pet.group.id

  tags = {
    Name = "something"
    App  = "c7n-test"
    Env  = "Dev"
  }

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.results.bucket}/output/"

      encryption_configuration {
        encryption_option = "SSE_KMS"
        kms_key_arn       = aws_kms_key.encrypt.arn
      }
    }
  }
}
