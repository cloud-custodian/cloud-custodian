provider "aws" {
  alias   = "testAccount"
  region  = "us-east-2"
  profile = "Testing"
}

terraform {
  backend "local" {
    path = "my.tfstate"
  }
  required_version = ">= 0.12"
  required_providers {
    aws = {
      version = ">= 2.7.0"
      source  = "hashicorp/aws"
    }
  }
}
