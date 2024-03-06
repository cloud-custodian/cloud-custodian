resource "random_pet" "names" {
  prefix = "tf-test"
  length = 2
}


resource "aws_athena_workgroup" "example" {
  name = random_pet.names.id

  configuration {
    publish_cloudwatch_metrics_enabled = true
  }
}
