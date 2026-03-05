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

resource "google_service_account" "legitimate_member" {
  account_id   = "iam-test-sa-wuc48fhtok"
  display_name = "Legitimate IAM Test Service Account"
  project      = var.google_project_id
}

resource "google_storage_bucket_iam_member" "sa_viewer" {
  bucket = google_storage_bucket.bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.legitimate_member.email}"
}

resource "google_storage_bucket_iam_member" "public_viewer" {
  bucket = google_storage_bucket.bucket.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

resource "google_storage_bucket_iam_member" "authenticated_legacy_reader" {
  bucket = google_storage_bucket.bucket.name
  role   = "roles/storage.legacyBucketReader"
  member = "allAuthenticatedUsers"
}
