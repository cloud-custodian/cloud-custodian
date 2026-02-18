provider "aws" {}

resource "aws_sqs_queue" "test_sqs" {
  name = "test-sqs-remove-matched-empty-sid"
}

resource "aws_sqs_queue_policy" "test_sqs_policy" {
  queue_url = aws_sqs_queue.test_sqs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "WithSid"
        Effect    = "Allow"
        Principal = "*"
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.test_sqs.arn
      },
      {
        Sid       = ""
        Effect    = "Allow"
        Principal = "*"
        Action    = "sqs:ReceiveMessage"
        Resource  = aws_sqs_queue.test_sqs.arn
      },
      {
        Sid    = "SameAccount"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "sqs:DeleteMessage"
        Resource = aws_sqs_queue.test_sqs.arn
      }
    ]
  })
}

data "aws_caller_identity" "current" {}
