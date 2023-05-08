provider "aws" {
  region = "us-west-2"
}

resource "aws_cloudwatch_log_group" "test_group" {
  name = uuid()

  tags = {
    Environment = "production"
    App         = "Foie"
  }
}
