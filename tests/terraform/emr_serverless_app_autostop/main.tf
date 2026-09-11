resource "aws_emrserverless_application" "autostop_enabled" {
  name          = "c7n-test-emr-serverless-autostop-enabled"
  release_label = "emr-6.9.0"
  type          = "Spark"

  auto_stop_configuration {
    enabled              = true
    idle_timeout_minutes = 15
  }
}

resource "aws_emrserverless_application" "autostop_disabled" {
  name          = "c7n-test-emr-serverless-autostop-disabled"
  release_label = "emr-6.9.0"
  type          = "Spark"

  auto_stop_configuration {
    enabled = false
  }
}
