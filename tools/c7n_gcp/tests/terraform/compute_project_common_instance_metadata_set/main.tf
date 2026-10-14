variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project               = var.google_project_id
  billing_project       = var.google_project_id
  user_project_override = true
}

resource "google_compute_project_metadata_item" "default" {
  project = var.google_project_id
  key     = "c7n-test-key"
  value   = "initial-value"
}
