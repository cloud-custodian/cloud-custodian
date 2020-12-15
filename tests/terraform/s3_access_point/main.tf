

resource "aws_s3_bucket" "example" {
  bucket = "example-abc-123"
}

resource "aws_s3_access_point" "example" {
  bucket = aws_s3_bucket.example.id
  name   = "ap-example-abc-123"
  public_access_block_configuration {
    block_public_policy = false
    restrict_public_buckets = false
  }
}  

