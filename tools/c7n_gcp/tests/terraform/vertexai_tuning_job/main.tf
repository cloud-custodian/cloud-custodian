provider "google" {}

# Infrastructure for the Vertex AI Tuning Job tests. The tuning jobs
# themselves have no Terraform resource and are created via API in the
# test code (see create_tuning_job in test_vertexai.py), then cancelled.

resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_storage_bucket" "tuning_data" {
  name          = "c7n-vertex-tune-${random_id.suffix.hex}"
  location      = "us-central1"
  force_destroy = true

  uniform_bucket_level_access = true
}

resource "google_storage_bucket_object" "training_data" {
  name   = "train.jsonl"
  bucket = google_storage_bucket.tuning_data.name
  source = "${path.module}/train.jsonl"
}

# Service account attached to a tuning job, standing in for an
# organization-approved tuning service account.
resource "google_service_account" "tuning" {
  account_id   = "c7n-tune-${random_id.suffix.hex}"
  display_name = "c7n Vertex AI tuning test"
}

resource "google_storage_bucket_iam_member" "tuning_data_reader" {
  bucket = google_storage_bucket.tuning_data.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.tuning.email}"
}

resource "google_project_iam_member" "tuning_aiplatform_user" {
  project = google_service_account.tuning.project
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.tuning.email}"
}

# The Tuning Service Agent impersonates the custom service account while
# running the job. Google creates this agent on a project's first tuning
# job, so the binding fails in a project that has never run one. See the
# recording note in test_vertexai_tuning_job_field_filters.
resource "google_service_account_iam_member" "tuning_agent_token_creator" {
  service_account_id = google_service_account.tuning.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${google_storage_bucket.tuning_data.project_number}@gcp-sa-vertex-tune.iam.gserviceaccount.com"
}

output "job_display_name" {
  value = "c7n-test-tuning-job-${terraform.workspace}-${random_id.suffix.hex}"
}

output "training_data_uri" {
  value = "gs://${google_storage_bucket.tuning_data.name}/${google_storage_bucket_object.training_data.name}"
}

output "service_account_email" {
  value = google_service_account.tuning.email
}
