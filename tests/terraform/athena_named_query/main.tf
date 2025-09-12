resource "random_pet" "bucket" {
  prefix = "tf-test"
  length = 2
}

resource "random_pet" "db" {
  prefix    = "tf_test"
  length    = 2
  separator = "_"
}

resource "aws_s3_bucket" "hoge" {
  bucket        = random_pet.bucket.id
  force_destroy = true
}

resource "aws_kms_key" "test" {
  deletion_window_in_days = 7
  description             = "Athena KMS Key"
}

resource "aws_athena_database" "hoge" {
  name   = random_pet.db.id
  bucket = aws_s3_bucket.hoge.id
}

resource "aws_athena_named_query" "foo" {
  name     = "bar"
  database = aws_athena_database.hoge.name
  query    = "SELECT * FROM ${aws_athena_database.hoge.name} limit 10;"
}
