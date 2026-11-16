provider "aws" {
  region = "us-east-1"
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

resource "random_integer" "trail" {
  min = 1
  max = 50000
}

# one trail per test so the tests stay order independent
locals {
  prefix     = "c7n-selectors-${random_integer.trail.id}"
  trail_arn  = "arn:aws:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/${local.prefix}"
  trail_arns = [for t in ["advanced", "basic", "mismatch"] : "${local.trail_arn}-${t}"]
}

resource "aws_s3_bucket" "trail" {
  bucket_prefix = "c7n-selectors"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "trail" {
  bucket                  = aws_s3_bucket.trail.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "trail" {
  bucket = aws_s3_bucket.trail.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AWSCloudTrailAclCheck"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:GetBucketAcl"
        Resource  = aws_s3_bucket.trail.arn
        Condition = { StringEquals = { "AWS:SourceArn" = local.trail_arns } }
      },
      {
        Sid       = "AWSCloudTrailWrite"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.trail.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = local.trail_arns
            "s3:x-amz-acl"  = "bucket-owner-full-control"
          }
        }
      }
    ]
  })
}

resource "aws_cloudtrail" "advanced" {
  name                          = "${local.prefix}-advanced"
  s3_bucket_name                = aws_s3_bucket.trail.bucket
  include_global_service_events = false
  enable_logging                = false

  event_selector {
    read_write_type           = "All"
    include_management_events = true
  }

  depends_on = [aws_s3_bucket_policy.trail]
}

resource "aws_cloudtrail" "basic" {
  name                          = "${local.prefix}-basic"
  s3_bucket_name                = aws_s3_bucket.trail.bucket
  include_global_service_events = false
  enable_logging                = false

  event_selector {
    read_write_type           = "All"
    include_management_events = true
  }

  depends_on = [aws_s3_bucket_policy.trail]
}

resource "aws_cloudtrail" "mismatch" {
  name                          = "${local.prefix}-mismatch"
  s3_bucket_name                = aws_s3_bucket.trail.bucket
  include_global_service_events = false
  enable_logging                = false

  event_selector {
    read_write_type           = "All"
    include_management_events = true
  }

  depends_on = [aws_s3_bucket_policy.trail]
}
