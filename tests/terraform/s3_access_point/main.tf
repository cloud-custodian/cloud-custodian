
provider "aws" {
  default_tags {
    tags = {
      Env   = "Dev"
      App   = "CloudCustodian"
      Owner = "dev@example.com"
    }
  }
}


data "aws_caller_identity" "current" {}
data "aws_region" "current" {}


resource "random_pet" "bucket" {
  length    = 2
  separator = "-"
}

resource "aws_s3_bucket" "example" {
  bucket = "c7n-ap-${random_pet.bucket.id}"
}

resource "aws_s3_access_point" "example" {
  bucket = aws_s3_bucket.example.id
  name   = "c7n-ap-${random_pet.bucket.id}"
  public_access_block_configuration {
    block_public_policy     = false
    restrict_public_buckets = false
  }
  policy = templatefile("policy.json", { unique_suffix = random_pet.bucket.id, account_id = data.aws_caller_identity.current.account_id, region = data.aws_region.current.name })
}

