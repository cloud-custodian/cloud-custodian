


resource "random_pet" "names" {
}


resource "aws_cloudwatch_log_group" "test_group_1" {
  name = "${random_pet.names.id}-1"
  tags = {
    Application = "greeter"
  }
}


resource "aws_cloudwatch_log_group" "test_group_2" {
  name = "${random_pet.names.id}-2"
  tags = {
    Application = "login"
  }
}


resource "aws_cloudwatch_log_group" "test_group_3" {
  name = "${random_pet.names.id}-3"
  tags = {
    Bap = "login"
  }
}


resource "aws_cloudwatch_log_group" "test_group_4" {
  name = "${random_pet.names.id}-4"
  tags = {
    Application = "greep"
    Bap         = "greeter"
  }
}


