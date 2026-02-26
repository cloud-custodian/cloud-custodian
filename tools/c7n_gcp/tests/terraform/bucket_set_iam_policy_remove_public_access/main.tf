variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
}

resource "google_storage_bucket" "bucket" {
  name     = "iam-test-bucket-wuc48fhtok"
  location = "US"

  labels = {
    env = "default"
  }
}
