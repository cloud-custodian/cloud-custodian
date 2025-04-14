# Example lifted from
# https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_saml_provider

provider "aws" {
  region = "us-east-1"
}

resource "aws_iam_saml_provider" "test_saml_provider" {
  name                   = "testprovider"
  # Use example metadata from:
  # https://mocksaml.com/
  saml_metadata_document = file("${path.module}/saml-metadata.xml")
  # Add tag for easy filtering
  tags = {
    "Name" = "testprovider"
  }
}
