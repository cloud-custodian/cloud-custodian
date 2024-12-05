#fail case: no alarm for filter

provider "aws" {
  region = "us-east-1"
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

resource "random_integer" "trail" {
  min = 1
  max = 50000
}

resource "aws_s3_bucket" "fail-bucket" {
  bucket_prefix = "fail-trail-test-bucket-testing"
  force_destroy = true
  tags = {
    c7n = true
  }
}

resource "aws_s3_bucket_public_access_block" "fail-bucket-block" {
  bucket                  = aws_s3_bucket.fail-bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "fail-policy" {
  bucket = aws_s3_bucket.fail-bucket.id

  policy = <<POLICY
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AWSCloudTrailAclCheck20150319",
            "Effect": "Allow",
            "Principal": {
                "Service": "cloudtrail.amazonaws.com"
            },
            "Action": "s3:GetBucketAcl",
            "Resource": "arn:aws:s3:::${aws_s3_bucket.fail-bucket.bucket}",
            "Condition": {
                "StringEquals": {
                    "AWS:SourceArn": "arn:aws:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/fail-tf-trail-${random_integer.trail.id}"
                }
            }
        },
        {
            "Sid": "AWSCloudTrailWrite20150319",
            "Effect": "Allow",
            "Principal": {
                "Service": "cloudtrail.amazonaws.com"
            },
            "Action": "s3:PutObject",
            "Resource": "arn:aws:s3:::${aws_s3_bucket.fail-bucket.bucket}/*",
            "Condition": {
                "StringEquals": {
                    "AWS:SourceArn": "arn:aws:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/fail-tf-trail-${random_integer.trail.id}",
                    "s3:x-amz-acl": "bucket-owner-full-control"
                }
            }
        }
    ]
}
POLICY
}


resource "aws_iam_policy" "testing-policy-fail" {
  name_prefix = "fail-testing-trailtest_policy"
  path        = "/"
  description = "cloudtrail role policy"

  # Terraform's "jsonencode" function converts a
  # Terraform expression result to valid JSON syntax.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Effect   = "Allow"
        Resource = "*"
      },
    ]
  })
  depends_on = [aws_cloudwatch_log_stream.fail-log-stream]
  tags = {
    c7n = true
  }
}

resource "aws_iam_role" "fail-cloudtrail-cloudwatch-role" {
  name_prefix = "cloudtrail_cloudwatch_role-fail"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        },
        Action = "sts:AssumeRole"
      }
    ]
  })
  tags = {
    c7n = true
  }
  depends_on = [aws_iam_policy.testing-policy-fail]
}

resource "aws_iam_role_policy_attachment" "fail-cloudtrail-cloudwatch-role-policy-attachment" {
  role       = aws_iam_role.fail-cloudtrail-cloudwatch-role.name
  policy_arn = aws_iam_policy.testing-policy-fail.arn
  depends_on = [aws_iam_role.fail-cloudtrail-cloudwatch-role]

}

resource "aws_cloudwatch_log_group" "log-group-fail" {
  name_prefix = "fail-cloudtrail-test-group"
  tags = {
    c7n = true
  }
}

resource "aws_cloudwatch_log_stream" "fail-log-stream" {
  name           = "${data.aws_caller_identity.current.account_id}_CloudTrail_${data.aws_region.current.name}"
  log_group_name = aws_cloudwatch_log_group.log-group-fail.name
}

resource "aws_cloudtrail" "fail-cloudtrail" {
  name                          = "fail-tf-trail-${random_integer.trail.id}"
  s3_bucket_name                = aws_s3_bucket.fail-bucket.bucket
  s3_key_prefix                 = ""
  include_global_service_events = true
  is_multi_region_trail         = true
  cloud_watch_logs_group_arn    = "${aws_cloudwatch_log_group.log-group-fail.arn}:*"
  cloud_watch_logs_role_arn     = aws_iam_role.fail-cloudtrail-cloudwatch-role.arn

  event_selector {
    read_write_type           = "All"
    include_management_events = true

    data_resource {
      type = "AWS::S3::Object"

      # Make sure to append a trailing '/' to your ARN if you want
      # to monitor all objects in a bucket.
      values = ["${aws_s3_bucket.fail-bucket.arn}/"]
    }
  }
  tags = {
    c7n = true
  }
  depends_on = [
    aws_s3_bucket_policy.fail-policy
  ]
}

#filter for alarm
resource "aws_cloudwatch_log_metric_filter" "fail-metric-filter" {
  name           = "test-filter-name-fail-${random_integer.trail.id}"
  log_group_name = aws_cloudwatch_log_group.log-group-fail.name
  pattern        = "{ ($.eventName = ConsoleLogin) && ($.additionalEventData.MFAUsed != Yes) }"
  metric_transformation {
    name      = "no_mfa_console_signin_metric_fail"
    namespace = "ImportantMetrics"
    value     = "1"
  }
}



