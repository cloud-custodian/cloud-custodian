variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
  region  = "us-central1"
}

resource "google_logging_project_bucket_config" "test" {
  project        = var.google_project_id
  location       = "us-central1"
  bucket_id      = "c7n-log-bucket-set-retention"
  retention_days = 30

  description = "Cloud Custodian set retention test log bucket"
}
