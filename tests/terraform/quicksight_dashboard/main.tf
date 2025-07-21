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
  bucket       = aws_s3_bucket.example.id
  key          = "manifest.json"
  content      = jsonencode({
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
        Sid       = "AllowQuickSightService",
        Effect    = "Allow",
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

resource "aws_quicksight_data_source" "example" {
  data_source_id = "example-source"
  name           = "example-source"
  type           = "S3"


  parameters {
    s3 {
      manifest_file_location {
        bucket = aws_s3_bucket.example.bucket
        key    = aws_s3_object.manifest.key
      }
      
      role_arn       = aws_iam_role.quicksight_s3_role.arn
    }
  }
}

resource "aws_quicksight_data_set" "example" {
  data_set_id = "example-dataset"
  name        = "example-dataset"
  import_mode = "SPICE"

  physical_table_map {
    physical_table_map_id = "main"
    s3_source {
      data_source_arn = aws_quicksight_data_source.example.arn
      input_columns {
        name = "id"
        type = "STRING"
      }
      upload_settings {
        format = "CSV"
      }
    }
  }
}

# Dashboards

resource "aws_quicksight_dashboard" "tagged_dashboard" {
  dashboard_id        = "tagged-dashboard-id"
  name                = "tagged-dashboard-name"
  version_description = "basic version"

  definition {
    data_set_identifiers_declarations {
      data_set_arn = aws_quicksight_data_set.example.arn
      identifier   = "main"
    }

    sheets {
      title    = "Sheet"
      sheet_id = "sheet1"

      visuals {
        line_chart_visual {
          visual_id = "line1"
          title {
            format_text {
              plain_text = "Line Chart"
            }
          }
        }
      }
    }
  }
}

resource "aws_quicksight_dashboard" "untagged_dashboard" {
  dashboard_id        = "untagged-dashboard-id"
  name                = "untagged-dashboard-name"
  version_description = "version"

  definition {
    data_set_identifiers_declarations {
      data_set_arn = aws_quicksight_data_set.example.arn
      identifier   = "main"
    }

    sheets {
      title    = "Sheet"
      sheet_id = "sheet1"

      visuals {
        line_chart_visual {
          visual_id = "line1"
          title {
            format_text {
              plain_text = "Line Chart"
            }
          }
        }
      }
    }
  }
}
