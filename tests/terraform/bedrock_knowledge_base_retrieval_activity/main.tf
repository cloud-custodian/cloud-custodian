# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

provider "aws" {
  region = "us-east-1"
}

resource "random_id" "suffix" {
  byte_length = 2
}

locals {
  name = "c7n-kb-activity-${terraform.workspace}-${random_id.suffix.hex}"
  # From a role ARN, not aws_caller_identity, which writes the caller's login
  # into tf_resources.json.
  account_id = split(":", aws_iam_role.trail.arn)[4]
  trail_arn  = "arn:aws:cloudtrail:us-east-1:${local.account_id}:trail/${local.name}"
}

resource "aws_s3_bucket" "trail" {
  bucket        = local.name
  force_destroy = true
}

resource "aws_s3_bucket_policy" "trail" {
  bucket = aws_s3_bucket.trail.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:GetBucketAcl"
        Resource  = aws_s3_bucket.trail.arn
        Condition = { StringEquals = { "aws:SourceArn" = local.trail_arn } }
      },
      {
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.trail.arn}/AWSLogs/${local.account_id}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl"  = "bucket-owner-full-control"
            "aws:SourceArn" = local.trail_arn
          }
        }
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "trail" {
  name              = local.name
  retention_in_days = 1
}

resource "aws_iam_role" "trail" {
  name = "${local.name}-trail"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudtrail.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "trail" {
  role = aws_iam_role.trail.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.trail.arn}:*"
    }]
  })
}

resource "aws_cloudtrail" "trail" {
  name                       = local.name
  s3_bucket_name             = aws_s3_bucket.trail.id
  cloud_watch_logs_group_arn = "${aws_cloudwatch_log_group.trail.arn}:*"
  cloud_watch_logs_role_arn  = aws_iam_role.trail.arn

  advanced_event_selector {
    name = "Bedrock knowledge base data events"

    field_selector {
      field  = "eventCategory"
      equals = ["Data"]
    }

    field_selector {
      field  = "resources.type"
      equals = ["AWS::Bedrock::KnowledgeBase"]
    }
  }

  depends_on = [aws_s3_bucket_policy.trail, aws_iam_role_policy.trail]
}

resource "aws_s3vectors_vector_bucket" "kb" {
  vector_bucket_name = local.name
  force_destroy      = true
}

resource "aws_s3vectors_index" "used" {
  index_name         = "used"
  vector_bucket_name = aws_s3vectors_vector_bucket.kb.vector_bucket_name
  data_type          = "float32"
  dimension          = 1024
  distance_metric    = "cosine"
}

resource "aws_s3vectors_index" "idle" {
  index_name         = "idle"
  vector_bucket_name = aws_s3vectors_vector_bucket.kb.vector_bucket_name
  data_type          = "float32"
  dimension          = 1024
  distance_metric    = "cosine"
}

resource "aws_s3vectors_index" "canary" {
  index_name         = "canary"
  vector_bucket_name = aws_s3vectors_vector_bucket.kb.vector_bucket_name
  data_type          = "float32"
  dimension          = 1024
  distance_metric    = "cosine"
}

resource "aws_iam_role" "kb" {
  name = "${local.name}-kb"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = local.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "kb" {
  role = aws_iam_role.kb.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "bedrock:InvokeModel"
        Resource = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
      },
      {
        Effect = "Allow"
        Action = [
          "s3vectors:GetIndex",
          "s3vectors:QueryVectors",
          "s3vectors:PutVectors",
          "s3vectors:GetVectors",
          "s3vectors:DeleteVectors",
        ]
        Resource = [
          aws_s3vectors_index.used.index_arn,
          aws_s3vectors_index.idle.index_arn,
          aws_s3vectors_index.canary.index_arn,
        ]
      },
    ]
  })
}

resource "aws_bedrockagent_knowledge_base" "used" {
  name     = "${local.name}-used"
  role_arn = aws_iam_role.kb.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
    }
  }

  storage_configuration {
    type = "S3_VECTORS"
    s3_vectors_configuration {
      index_arn = aws_s3vectors_index.used.index_arn
    }
  }

  depends_on = [aws_iam_role_policy.kb]
}

resource "aws_bedrockagent_knowledge_base" "idle" {
  name     = "${local.name}-idle"
  role_arn = aws_iam_role.kb.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
    }
  }

  storage_configuration {
    type = "S3_VECTORS"
    s3_vectors_configuration {
      index_arn = aws_s3vectors_index.idle.index_arn
    }
  }

  depends_on = [aws_iam_role_policy.kb]
}

resource "aws_bedrockagent_knowledge_base" "canary" {
  name     = "${local.name}-canary"
  role_arn = aws_iam_role.kb.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
    }
  }

  storage_configuration {
    type = "S3_VECTORS"
    s3_vectors_configuration {
      index_arn = aws_s3vectors_index.canary.index_arn
    }
  }

  depends_on = [aws_iam_role_policy.kb]
}

output "used_knowledge_base_arn" {
  value = aws_bedrockagent_knowledge_base.used.arn
}

output "idle_knowledge_base_arn" {
  value = aws_bedrockagent_knowledge_base.idle.arn
}

output "canary_knowledge_base_arn" {
  value = aws_bedrockagent_knowledge_base.canary.arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.trail.name
}
