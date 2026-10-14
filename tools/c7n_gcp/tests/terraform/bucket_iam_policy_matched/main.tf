variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
}

resource "google_storage_bucket" "bucket" {
  name     = "c7n-iam-matched-test-x7r2k"
  location = "US"

  labels = {
    env = "test"
  }
}

resource "google_service_account" "sa" {
  account_id   = "c7n-iam-matched-sa-x7r2k"
  display_name = "C7N IAM Matched Test SA"
  project      = var.google_project_id
}

# Matches roles/*admin via value_type: normalize (objectAdmin -> objectadmin)
resource "google_storage_bucket_iam_member" "sa_object_admin" {
  bucket = google_storage_bucket.bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.sa.email}"
}

# Matches roles/*admin directly (already lowercase)
resource "google_storage_bucket_iam_member" "sa_admin" {
  bucket = google_storage_bucket.bucket.name
  role   = "roles/storage.admin"
  member = "serviceAccount:${google_service_account.sa.email}"
}

# Used for exact-role-match testing (op: in); does NOT match roles/*admin
resource "google_storage_bucket_iam_member" "sa_legacy_owner" {
  bucket = google_storage_bucket.bucket.name
  role   = "roles/storage.legacyBucketOwner"
  member = "serviceAccount:${google_service_account.sa.email}"
}

# Never matches any test pattern — verifies viewer bindings are always preserved
resource "google_storage_bucket_iam_member" "sa_viewer" {
  bucket = google_storage_bucket.bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.sa.email}"
}

# Non-SA member in an admin role — verifies SA-only patterns leave other members intact
resource "google_storage_bucket_iam_member" "non_sa_object_admin" {
  bucket = google_storage_bucket.bucket.name
  role   = "roles/storage.objectAdmin"
  member = "allAuthenticatedUsers"
}
