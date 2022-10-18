resource "aws_iam_role" "this" {
  name = "iam_for_${local.codebuild_project_name}"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "codebuild.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF
}

resource "aws_cloudwatch_log_group" "this" {
  name = "/aws/codebuild/${local.codebuild_project_name}"

  tags = {}
}

resource "aws_codebuild_project" "this" {
  name           = local.codebuild_project_name
  service_role = aws_iam_role.this.arn

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/standard:1.0"
    type                        = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
  }

  source {
    type            = "NO_SOURCE"
    buildspec       = "version: 0.2\n\nphases:\n  build:\n    commands:\n       - echo \"testing\"\n"
  }

  tags = {
    copy_tag1     = "value1",
    copy_tag2     = "value2",
    not_copy_tag1 = "value3",
  }

  depends_on = [
    aws_cloudwatch_log_group.this,
    aws_iam_role.this,
  ]
}