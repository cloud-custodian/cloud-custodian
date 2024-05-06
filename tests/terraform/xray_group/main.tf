resource "aws_xray_group" "example" {
  group_name        = "example"
  filter_expression = "responsetime > 5"

  insights_configuration {
    insights_enabled      = true
    notifications_enabled = true
  }
}
