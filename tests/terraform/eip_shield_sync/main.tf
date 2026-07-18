provider "aws" {
  region = "us-east-1"
}

resource "aws_eip" "protected" {
  domain = "vpc"
  tags = {
    c7n-test = "protected"
  }
}

resource "aws_eip" "unprotected" {
  domain = "vpc"
  tags = {
    c7n-test = "unprotected"
  }
}

resource "aws_shield_protection" "shield_protection" {
  name         = "shield-protection"
  resource_arn = replace(aws_eip.protected.arn, "elastic-ip", "eip-allocation")
}