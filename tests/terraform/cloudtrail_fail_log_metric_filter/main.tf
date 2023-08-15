provider "aws" {
  region = "us-east-1"
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

resource "random_integer" "trail" {
  min = 1
  max = 50000
}

resource "aws_s3_bucket" "success-1" {
  bucket_prefix = "trail-test-bucket"
  force_destroy = true
  tags = {
    c7n = true
  }
}

resource "aws_s3_bucket_public_access_block" "block-access-bucket" {
  bucket                  = aws_s3_bucket.success-1.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "success-1-policy" {
  bucket = aws_s3_bucket.success-1.id

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
            "Resource": "arn:aws:s3:::${aws_s3_bucket.success-1.bucket}",
            "Condition": {
                "StringEquals": {
                    "AWS:SourceArn": "arn:aws:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/tf-trail-${random_integer.trail.id}"
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
            "Resource": "arn:aws:s3:::${aws_s3_bucket.success-1.bucket}/*",
            "Condition": {
                "StringEquals": {
                    "AWS:SourceArn": "arn:aws:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/tf-trail-${random_integer.trail.id}",
                    "s3:x-amz-acl": "bucket-owner-full-control"
                }
            }
        }
    ]
}
POLICY
}


resource "aws_iam_policy" "testing-policy" {
  name_prefix = "testing-trailtest_policy"
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
  depends_on = [aws_cloudwatch_log_stream.success-log-stream]
  tags = {
    c7n = true
  }
}

resource "aws_iam_role" "testing-cloudtrail-cloudwatch-role" {
  name_prefix = "testing-cloudtrail_cloudwatch_role"
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
  depends_on = [aws_iam_policy.testing-policy]
}

resource "aws_iam_role_policy_attachment" "testing_cloudtrail_cloudwatch_role_policy_attachment" {
  role       = aws_iam_role.testing-cloudtrail-cloudwatch-role.name
  policy_arn = aws_iam_policy.testing-policy.arn
  depends_on = [aws_iam_role.testing-cloudtrail-cloudwatch-role]

}

resource "aws_cloudwatch_log_group" "success-5" {
  name = "cloudtrail-test-group-${random_integer.trail.id}"
  tags = {
    c7n = true
  }
}

resource "aws_cloudwatch_log_stream" "success-log-stream" {
  name           = "${data.aws_caller_identity.current.account_id}_CloudTrail_${data.aws_region.current.name}"
  log_group_name = aws_cloudwatch_log_group.success-5.name
}

resource "aws_cloudtrail" "success-2" {
  name                          = "tf-trail-${random_integer.trail.id}"
  s3_bucket_name                = aws_s3_bucket.success-1.bucket
  s3_key_prefix                 = "prefix"
  include_global_service_events = true
  is_multi_region_trail         = true
  cloud_watch_logs_group_arn    = "${aws_cloudwatch_log_group.success-5.arn}:*"
  cloud_watch_logs_role_arn     = aws_iam_role.testing-cloudtrail-cloudwatch-role.arn

  event_selector {
    read_write_type           = "All"
    include_management_events = true

    data_resource {
      type = "AWS::S3::Object"

      # Make sure to append a trailing '/' to your ARN if you want
      # to monitor all objects in a bucket.
      values = ["${aws_s3_bucket.success-1.arn}/"]
    }
  }
  tags = {
    c7n = true
  }
  depends_on = [aws_s3_bucket_policy.success-1-policy]
}

#filter for alarm
resource "aws_cloudwatch_log_metric_filter" "success-3" {
  name           = "test-filter-name-${random_integer.trail.id}"
  log_group_name = aws_cloudwatch_log_group.success-5.name
  pattern        = "{ ($.eventName = ConsoleLogin) && ($.additionalEventData.MFAUsed != Yes) }"
  metric_transformation {
    name      = "no_mfa_console_signin_metric_1"
    namespace = "ImportantMetrics"
    value     = "1"
  }
}

#alarm
#check hwo to refer to metric transformation name from filter
resource "aws_cloudwatch_metric_alarm" "success-4" {
  alarm_name          = "NoMFAConsoleLoginAlarm-${random_integer.trail.id}"
  metric_name         = aws_cloudwatch_log_metric_filter.success-3.metric_transformation[0].name
  threshold           = "0"
  statistic           = "Sum"
  comparison_operator = "GreaterThanThreshold"
  datapoints_to_alarm = "1"
  evaluation_periods  = "1"
  period              = "60"
  namespace           = "ImportantMetrics"
  alarm_actions       = [aws_sns_topic.success-sns-topic.arn]
  tags = {
    c7n = true
  }
}

resource "aws_sns_topic" "success-sns-topic" {
  name = "mfa-notification-topic-${random_integer.trail.id}"
  tags = {
    c7n = true
  }
}

resource "aws_sqs_queue" "success_sqs_queue" {
  name = "mfa-sqs-topic-${random_integer.trail.id}"
  tags = {
    c7n = true
  }
}

resource "aws_sns_topic_subscription" "user_updates_sqs_target" {
  topic_arn = aws_sns_topic.success-sns-topic.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.success_sqs_queue.arn
}

