resource "aws_iam_group" "sandbox_evs" {
  name = "sandbox_developers"
  path = "/users/"
}