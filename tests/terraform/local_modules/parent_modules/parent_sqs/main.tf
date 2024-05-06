resource "aws_sqs_queue" "parent_queue" {
  name                      = "parent_queue"
  delay_seconds             = 90
  max_message_size          = 2048
  message_retention_seconds = 86400
  receive_wait_time_seconds = 10
}
