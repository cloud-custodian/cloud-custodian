variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
}

resource "random_id" "suffix" {
  byte_length = 2
}

# Holds a role from each set; the admin grant is conditional, so it is read
# back as roles/cloudkms.admin_withcond_<hash>
resource "google_service_account" "bad" {
  account_id   = "c7n-sod-bad-${random_id.suffix.hex}"
  display_name = "C7N Separation of Duties Bad SA"
  project      = var.google_project_id
}

resource "google_project_iam_member" "bad_admin" {
  project = var.google_project_id
  role    = "roles/cloudkms.admin"
  member  = "serviceAccount:${google_service_account.bad.email}"

  condition {
    title      = "c7n-sod-bad-${random_id.suffix.hex}"
    expression = "request.time < timestamp(\"2100-01-01T00:00:00Z\")"
  }
}

resource "google_project_iam_member" "bad_encrypter_decrypter" {
  project = var.google_project_id
  role    = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member  = "serviceAccount:${google_service_account.bad.email}"
}

# In neither set, so it is left out of the annotation
resource "google_project_iam_member" "bad_viewer" {
  project = var.google_project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.bad.email}"
}

# Holds only roles/cloudkms.admin, so it is never reported
resource "google_service_account" "good" {
  account_id   = "c7n-sod-good-${random_id.suffix.hex}"
  display_name = "C7N Separation of Duties Good SA"
  project      = var.google_project_id
}

resource "google_project_iam_member" "good_admin" {
  project = var.google_project_id
  role    = "roles/cloudkms.admin"
  member  = "serviceAccount:${google_service_account.good.email}"
}
