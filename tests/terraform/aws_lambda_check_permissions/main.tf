data "archive_file" "lambda_package" {
  type        = "zip"
  output_path = "${path.module}/lambda_package.zip"

  source {
    content  = <<EOF
def lambda_handler(event, context):
  print('Hello from Lambda')
EOF
    filename = "${path.module}/handler.py"
  }
}

resource "aws_iam_role" "lambda" {
  name_prefix = "c7n_test_check_permissions"

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

resource "aws_lambda_function" "test_check_permissions" {
  filename      = data.archive_file.lambda_package.output_path
  runtime       = "python3.8"
  handler       = "handler.lambda_handler"
  function_name = "c7n_test_check_permissions"
  role          = aws_iam_role.lambda.arn
}
