locals {
  default_tags = {
    Environment = "sandbox"
  }
}

variable "tags" {
  default = {
    Environment = "sandbox"
  }
}

data "http" "example" {
  url = "https://checkpoint-api.hashicorp.com/v1/check/terraform"

  request_headers = {
    Accept = "application/json"
  }
}

resource "aws_db_parameter_group" "with_local" {
  name   = "with-local"
  family = "postgres16"

  tags = merge(
    local.default_tags,
    {
      ApplyTimeVal = data.http.example.status_code
    }
  )
}

resource "aws_db_parameter_group" "with_var" {
  name   = "with-vars"
  family = "postgres16"

  tags = merge(
    var.tags,
    {
      ApplyTimeVal = data.http.example.status_code
    }
  )
}

resource "aws_db_parameter_group" "untagged" {
  name   = "untagged"
  family = "postgres16"
}
