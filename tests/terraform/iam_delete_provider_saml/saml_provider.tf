# Example lifted from
https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_saml_provider

provider "aws" {
  region = "us-east-1"
}

resource "aws_iam_saml_provider" "test_saml_provider" {
  name                   = "testprovider"
  saml_metadata_document = file("saml-metadata.xml")
}
