resource "aws_cloudwatch_log_group" "this" {
  name = "/aws/codebuild/no_related_lambda_function"

  tags = {}
}