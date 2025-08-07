provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "example" {
  bucket = "c7ntest-quicksight-test-bucket"
}

resource "aws_s3_object" "data" {
  bucket       = aws_s3_bucket.example.id
  key          = "data.csv"
  source       = "${path.module}/data.csv"
  content_type = "text/csv"
}

resource "aws_s3_object" "manifest" {
  bucket = aws_s3_bucket.example.id
  key    = "manifest.json"
  content = jsonencode({
    fileLocations = [
      {
        URIs = ["s3://${aws_s3_bucket.example.bucket}/data.csv"]
      }
    ],
    globalUploadSettings = {
      format = "CSV"
    }
  })
  content_type = "application/json"
}

resource "aws_s3_bucket_policy" "quicksight_access" {
  bucket = aws_s3_bucket.example.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid    = "AllowQuickSightService",
        Effect = "Allow",
        Principal = {
          Service = "quicksight.amazonaws.com"
        },
        Action = ["s3:GetObject", "s3:ListBucket"],
        Resource = [
          aws_s3_bucket.example.arn,
          "${aws_s3_bucket.example.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role" "quicksight_s3_role" {
  name = "QuickSightS3AccessRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = {
        Service = "quicksight.amazonaws.com"
      },
      Action = "sts:AssumeRole"
    }]
  })
}

# 6. Policy for that role to read the bucket
resource "aws_iam_policy" "quicksight_s3_policy" {
  name = "QuickSightS3AccessPolicy"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = ["s3:GetObject", "s3:ListBucket"],
        Resource = [
          aws_s3_bucket.example.arn,
          "${aws_s3_bucket.example.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "quicksight_s3_role_attach" {
  role       = aws_iam_role.quicksight_s3_role.name
  policy_arn = aws_iam_policy.quicksight_s3_policy.arn
}

resource "aws_quicksight_data_source" "tagged_example" {
  data_source_id = "tagged-example-source"
  name           = "tagged-example-source"
  type           = "S3"
  tags           = { "Owner" : "c7n" }

  parameters {
    s3 {
      manifest_file_location {
        bucket = aws_s3_bucket.example.bucket
        key    = aws_s3_object.manifest.key
      }

      role_arn = aws_iam_role.quicksight_s3_role.arn
    }
  }
}


resource "aws_quicksight_data_source" "untagged_example" {
  data_source_id = "untagged-example-source"
  name           = "untagged-example-source"
  type           = "S3"


  parameters {
    s3 {
      manifest_file_location {
        bucket = aws_s3_bucket.example.bucket
        key    = aws_s3_object.manifest.key
      }

      role_arn = aws_iam_role.quicksight_s3_role.arn
    }
  }
}
