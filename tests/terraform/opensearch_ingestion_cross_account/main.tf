data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "random_id" "suffix" {
  byte_length = 8
}

resource "aws_iam_role" "pipeline_role" {
  name = "osis-pipeline-role-${random_id.suffix.hex}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "osis-pipelines.amazonaws.com"
        }
      },
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::794038253860:root"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "pipeline_policy" {
  name = "osis-pipeline-policy-${random_id.suffix.hex}"
  role = aws_iam_role.pipeline_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetBucketLocation",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.sink.arn,
          "${aws_s3_bucket.sink.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_s3_bucket" "sink" {
  bucket        = "c7n-osis-sink-${random_id.suffix.hex}"
  force_destroy = true
}

resource "aws_cloudwatch_log_group" "pipeline_logs" {
  name = "/aws/vendedlogs/osis/c7n-pipeline-logs-${random_id.suffix.hex}"
}

resource "aws_osis_pipeline" "test" {
  pipeline_name = "c7n-test-${random_id.suffix.hex}"
  min_units     = 1
  max_units     = 1

  log_publishing_options {
    is_logging_enabled = true
    cloudwatch_log_destination {
      log_group = aws_cloudwatch_log_group.pipeline_logs.name
    }
  }

  pipeline_configuration_body = <<EOF
version: "2"
opensearch-pipeline:
  source:
    http:
      path: "/"
  sink:
    - s3:
        aws:
          sts_role_arn: "${aws_iam_role.pipeline_role.arn}"
          region: "${data.aws_region.current.id}"
        bucket: "${aws_s3_bucket.sink.bucket}"
        threshold:
          event_collect_timeout: "60s"
        codec:
          ndjson:
EOF
}
