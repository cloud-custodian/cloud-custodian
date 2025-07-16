resource "aws_s3_bucket" "example" {
  bucket = "c7ntest-quicksight-test-bucket"
}

resource "aws_s3_object" "manifest" {
  bucket = aws_s3_bucket.example.id
  key    = "manifest.json"
  content = <<EOF
{
  "fileLocations": [
    {
      "URIs": ["s3://${aws_s3_bucket.example.id}/data.csv"]
    }
  ],
  "globalUploadSettings": {
    "format": "CSV"
  }
}
EOF
}

resource "aws_quicksight_data_source" "example" {
    data_source_id = "example-source"
    name           = "example-source"
    type = "S3"
    parameters {
        s3 {
            manifest_file_location {
                bucket = aws_s3_bucket.example.id
                key    = aws_s3_object.manifest.key
            }
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

resource "aws_quicksight_dashboard" "example" {
  dashboard_id        = "example-id"
  name                = "example-name"
  version_description = "version"
  tags = {
    Owner = "c7n"
  }
  definition {
    data_set_identifiers_declarations {
      data_set_arn = aws_quicksight_data_set.example.arn
      identifier   = "main"
    }
    sheets {
      title    = "Simple Sheet"
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