resource "aws_emrserverless_application" "test" {
  name          = "c7n-test-emr-serverless-delete"
  release_label = "emr-6.9.0"
  type          = "Spark"
}
