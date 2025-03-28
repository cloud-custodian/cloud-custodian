data "aws_region" "example" {}

data "terraform_remote_state" "example" {
  backend = "remote"

  config = {
    organization = "c7n"
    workspaces = {
      name = "testing"
    }
  }
}

variable "tags" {
  type = map(string)
  default = {
    Var1 = "${data.aws_region.example.name}-test"
    Var2 = "test"
    Var3 = data.aws_region.example.name
  }
}

resource "aws_instance" "tagged_known_preset_values" {
  tags = merge(
    var.tags,
    {
      "Environment" = "sandbox"
    }
  )
}

resource "aws_instance" "tagged_unknown_values" {
  tags = merge(
    var.tags,
    {
      "Unknown" : data.terraform_remote_state.example.outputs.app_name
    },
    {
      "Environment" = "sandbox"
    }
  )
}

resource "aws_instance" "untagged" {
  name = "untagged"
}
