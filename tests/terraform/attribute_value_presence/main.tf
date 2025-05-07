data "aws_caller_identity" "current" {}

resource "aws_iam_role" "attribute_with_direct_reference" {
    permissions_boundary = data.aws_caller_identity.current.account_id
}

resource "aws_iam_role" "attribute_with_interpolated_reference" {
    permissions_boundary = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/BoundaryPolicy"
}

resource "aws_iam_role" "attribute_not_present" {}
