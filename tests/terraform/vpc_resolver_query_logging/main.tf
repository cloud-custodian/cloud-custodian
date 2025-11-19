provider "aws" {
  region = "us-east-1"
}

data "aws_vpc" "flow_log_vpc" {
  id = "vpc-0503a8b9ddbb3a5c5" # ECS c7n-test-cluster - VPC
}

data "aws_vpc" "no_flow_log_vpc" {
  id = "vpc-029d7b65096a4717d" # policy-test-vpc
}

resource "aws_flow_log" "example" {
  iam_role_arn    = aws_iam_role.flow_log_role.arn
  log_destination = aws_cloudwatch_log_group.example.arn
  traffic_type    = "ALL"
  vpc_id          = data.aws_vpc.flow_log_vpc.id
}

resource "aws_cloudwatch_log_group" "example" {
  name = "vpc-flow-logs-test"
}

resource "aws_iam_role" "flow_log_role" {
  name_prefix = "flow-logs-role-"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "",
      "Effect": "Allow",
      "Principal": {
        "Service": "vpc-flow-logs.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
}

resource "aws_iam_role_policy" "flow_logs_policy" {
  name_prefix = "flow-logs-policy-"
  role        = aws_iam_role.flow_log_role.id

  policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams"
      ],
      "Effect": "Allow",
      "Resource": "*"
    }
  ]
}
EOF
}

resource "aws_s3_bucket" "resolver_logs" {
  bucket_prefix = "resolver-query-logs-"
  force_destroy = true
}

resource "aws_iam_role" "resolver_logs_role" {
  name_prefix = "resolver-logs-"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "route53resolver.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "resolver_logs_policy" {
  role = aws_iam_role.resolver_logs_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action   = ["s3:PutObject"]
      Effect   = "Allow"
      Resource = "${aws_s3_bucket.resolver_logs.arn}/*"
    }]
  })
}

resource "aws_route53_resolver_query_log_config" "test" {
  name            = "test-resolver-query-log-config"
  destination_arn = aws_s3_bucket.resolver_logs.arn
}

resource "aws_route53_resolver_query_log_config_association" "test" {
  resolver_query_log_config_id = aws_route53_resolver_query_log_config.test.id
  resource_id                  = data.aws_vpc.flow_log_vpc.id
}

output "vpc_with_resolver_logging_id" {
  value = data.aws_vpc.flow_log_vpc.id
}

output "vpc_without_resolver_logging_id" {
  value = data.aws_vpc.no_flow_log_vpc.id
}

output "resolver_log_config_id" {
  value = aws_route53_resolver_query_log_config.test.id
}

output "resolver_log_bucket" {
  value = aws_s3_bucket.resolver_logs.bucket
}