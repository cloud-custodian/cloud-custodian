resource "aws_iam_role" "this" {
  name = "iam_for_${local.lambda_function_name}"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF
}

resource "aws_cloudwatch_log_group" "this" {
  name = "/aws/lambda/${local.lambda_function_name}"

  tags = {}
}

resource "aws_lambda_function" "this" {
  function_name = local.lambda_function_name
  role          = aws_iam_role.this.arn
  runtime       = "python3.8"
  filename      = data.archive_file.lambda_package.output_path
  handler       = "handler.lambda_handler"

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