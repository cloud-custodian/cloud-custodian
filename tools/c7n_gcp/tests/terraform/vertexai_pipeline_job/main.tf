provider "google" {}

resource "random_id" "suffix" {
  byte_length = 4
}

data "google_project" "current" {}

resource "google_storage_bucket" "pipeline" {
  name          = "c7n-pipeline-${random_id.suffix.hex}"
  location      = "US"
  force_destroy = true
}

resource "google_storage_bucket_iam_member" "pipeline" {
  bucket = google_storage_bucket.pipeline.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}

output "pipeline_root" {
  value = "gs://${google_storage_bucket.pipeline.name}/pipelines"
}

output "service_account" {
  value = "${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}
