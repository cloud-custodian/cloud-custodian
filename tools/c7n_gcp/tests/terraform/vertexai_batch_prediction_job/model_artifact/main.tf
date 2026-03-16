terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  region = "us-central1"
}

resource "google_storage_bucket" "vertex_test_models" {
  name     = "${var.project_id}-vertex-test-models"
  location = "US" # multi-region → works for us-central1 + us-east1

  uniform_bucket_level_access = true

  # Safe default for test environments
  force_destroy = true
}

variable "project_id" {
  description = "GCP project ID to use for creating resources"
  type        = string
}

