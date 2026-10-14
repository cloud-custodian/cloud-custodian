provider "google" {}

resource "random_id" "suffix" {
  byte_length = 2
}

locals {
  suffix = "${terraform.workspace}-${random_id.suffix.hex}"
}

resource "google_vertex_ai_endpoint" "default" {
  name         = "c7n-endpoint-${local.suffix}"
  display_name = "c7n-endpoint-${local.suffix}"
  location     = "us-central1"
  region       = "us-central1"
}

resource "google_storage_bucket" "artifacts" {
  name          = "c7n-vertex-metrics-${local.suffix}"
  location      = "US"
  force_destroy = true

  uniform_bucket_level_access = true
}
