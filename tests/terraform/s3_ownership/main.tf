resource "aws_s3_bucket" "no_ownership_controls" {
  bucket_prefix = "c7ntest-"
}

resource "aws_s3_bucket" "owner_preferred" {
  bucket_prefix = "c7ntest-"
}

resource "aws_s3_bucket" "owner_enforced" {
  bucket_prefix = "c7ntest-"
}

resource "aws_s3_bucket_ownership_controls" "object_writer" {
  bucket = aws_s3_bucket.owner_preferred.id

  rule {
    object_ownership = "ObjectWriter"
  }
}

resource "aws_s3_bucket_ownership_controls" "owner_preferred" {
  bucket = aws_s3_bucket.owner_preferred.id

  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_ownership_controls" "owner_enforced" {
  bucket = aws_s3_bucket.owner_enforced.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}
