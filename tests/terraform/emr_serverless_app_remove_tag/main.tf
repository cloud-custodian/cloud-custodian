resource "aws_emrserverless_application" "test" {
  name          = "c7n-test-emr-serverless-remove-tag"
  release_label = "emr-6.9.0"
  type          = "Spark"

  tags = {
    foo = "bar"
  }
}
