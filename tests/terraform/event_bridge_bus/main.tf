resource "aws_cloudwatch_event_bus" "messenger" {
  name = "chat-messages"
  tags = {
    Env = "Sandbox"
  }
}

resource "aws_cloudwatch_event_permission" "DevAccountAccess" {
  principal      = "123456789012"
  statement_id   = "DevAccountAccess"
  event_bus_name = aws_cloudwatch_event_bus.messenger.name
}
