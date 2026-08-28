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
  account_id   = "c7n-audit-config-test"
  display_name = "C7N Audit Config Test SA"
  project      = var.google_project_id
}

# Give the SA a viewer role so bindings are present from the start;
# the combined test also exercises adding roles/logging.viewer via add-bindings.
resource "google_project_iam_member" "sa_viewer" {
  project = var.google_project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.sa.email}"
}
