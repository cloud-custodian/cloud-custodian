terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "4.49.0"
    }
  }
}

provider "aws" {
  region = "us-east-2"
}

module "module_in_parent_dir" {
  source = "../parent_modules/parent_sqs"
}

module "module_in_child_dir" {
  source = "./child_modules/child_sqs"
}
