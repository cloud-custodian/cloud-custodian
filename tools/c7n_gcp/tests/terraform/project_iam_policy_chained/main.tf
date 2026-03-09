variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
}

data "google_project" "project" {
  project_id = var.google_project_id
}

resource "google_service_account" "sa" {
  account_id   = "c7n-iam-chained-x7r2k"
  display_name = "C7N IAM Chained Filters Test SA"
  project      = var.google_project_id
}

# Matched by first iam-policy filter (op: glob, value: 'roles/owner')
resource "google_project_iam_member" "sa_owner" {
  project = var.google_project_id
  role    = "roles/owner"
  member  = "serviceAccount:${google_service_account.sa.email}"
}

# Matched by second iam-policy filter (op: glob, value: 'roles/editor')
resource "google_project_iam_member" "sa_editor" {
  project = var.google_project_id
  role    = "roles/editor"
  member  = "serviceAccount:${google_service_account.sa.email}"
}

# Never matched — verifies viewer binding is preserved
resource "google_project_iam_member" "sa_viewer" {
  project = var.google_project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.sa.email}"
}
