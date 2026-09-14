resource "aws_emrserverless_application" "test" {
  name          = "c7n-test-emr-serverless-tag"
  release_label = "emr-6.9.0"
  type          = "Spark"
}
