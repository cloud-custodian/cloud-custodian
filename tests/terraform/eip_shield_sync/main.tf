data "aws_availability_zones" "available" {}
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

resource "aws_eip" "first" {
  domain = "vpc"
}

resource "aws_eip" "second" {
  domain = "vpc"
}

resource "aws_shield_protection" "compliant-shield-advanced-protection" {
  name         = "compliant-shield-advanced-protection"
  resource_arn = "arn:aws:ec2:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:eip-allocation/${aws_eip.first.id}"

  tags = {
    Environment = "Dev"
  }
}