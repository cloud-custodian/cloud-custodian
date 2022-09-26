resource "aws_cloudwatch_log_group" "this" {
  name = "/aws/lambda/no_related_lambda_function"

  tags = {}
}