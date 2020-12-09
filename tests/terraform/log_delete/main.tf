resource "aws_cloudwatch_log_group" "test_group" {
  name = "Yada"

  tags = {
    Environment = "production"
    App = "Foie"
  }
}
