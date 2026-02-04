data "aws_caller_identity" "current" {}

resource "aws_kms_key" "cwe" {
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        },
        Action   = "kms:*"
        Resource = "*"
      },
      {
        "Effect" : "Allow",
        "Principal" : {
          "Service" : "events.amazonaws.com"
        },
        "Action" : [
          "kms:Decrypt",
          "kms:DescribeKey",
          "kms:GenerateDataKey"
        ],
        "Resource" : "*"
      }
    ]
  })
}

resource "aws_kms_alias" "cwe" {
  name          = "alias/test/cwe"
  target_key_id = aws_kms_key.cwe.key_id
}

resource "aws_cloudwatch_event_bus" "messenger" {
  name = "chat-messages"
  tags = {
    Env = "Sandbox"
  }
  kms_key_identifier = aws_kms_key.cwe.key_id
}

resource "aws_cloudwatch_event_permission" "DevAccountAccess" {
  principal      = "123456789012"
  statement_id   = "DevAccountAccess"
  event_bus_name = aws_cloudwatch_event_bus.messenger.name
}
