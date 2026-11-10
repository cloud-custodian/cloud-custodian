provider "google" {}

data "google_project" "project" {}

resource "google_service_account" "sa" {
  account_id   = "c7n-audit-wildcard"
  display_name = "C7N Audit Wildcard Test SA"
}

# An untouched binding the audit-only setIamPolicy must preserve.
resource "google_project_iam_member" "sa_viewer" {
  project = data.google_project.project.project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.sa.email}"
}

# Exemptions on allServices and on a specific service, so service: '*' has to reach both.
resource "google_project_iam_audit_config" "all_services" {
  project = data.google_project.project.project_id
  service = "allServices"

  audit_log_config {
    log_type         = "DATA_WRITE"
    exempted_members = ["serviceAccount:${google_service_account.sa.email}"]
  }
}

resource "google_project_iam_audit_config" "storage" {
  project = data.google_project.project.project_id
  service = "storage.googleapis.com"

  audit_log_config {
    log_type         = "DATA_READ"
    exempted_members = ["serviceAccount:${google_service_account.sa.email}"]
  }
}
