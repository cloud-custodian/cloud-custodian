resource "aws_s3_bucket" "example" {
  bucket_prefix = "c7ntest"
  acl           = "private"

  tags = {
    original-tag = "original-value"
  }
}
