terraform {
  required_providers {
    tencentcloud = {
      source = "tencentcloudstack/tencentcloud"
    }
    oci = {
      source = "oracle/oci"
    }
  }
}

resource "azurerm_resource_group" "example" {
  name     = "example-resources"
  location = "West Europe"
}


resource "aws_cloudwatch_log_group" "yada" {
  name = "Yada"
}


resource "google_storage_bucket" "static-site" {
  name     = "image-store.com"
  location = "EU"
}


resource "oci_logging_log_group" "test_log_group" {
  compartment_id = "abc"
  display_name   = "name"
}


resource "tencentcloud_cos_bucket" "private_sbucket" {
  bucket = "private-bucket-123"
  acl    = "private"
}
