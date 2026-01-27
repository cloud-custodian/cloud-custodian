resource "aws_iam_group" "sandbox_devs" {
  name = "sandbox_developers"
  path = "/users/"
}

resource "aws_iam_user" "sandbox_jill" {
  name = "sandbox_jill"
}

resource "aws_iam_group_membership" "sandbox_dev_members" {
  name  = "sandbox_dev_members"
  users = [aws_iam_user.sandbox_jill.name]
  group = aws_iam_group.sandbox_devs.name
}
