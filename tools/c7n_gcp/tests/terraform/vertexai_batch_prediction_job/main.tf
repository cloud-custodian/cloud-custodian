provider "google" {}

# This Terraform configuration creates the INFRASTRUCTURE needed for
# Vertex AI Batch Prediction Job tests. The actual batch prediction JOBS
# are created via API in the test code when recording (see test_vertexai.py).
#
# This follows the pattern used in other GCP tests where:
# - Terraform creates persistent infrastructure (buckets, models, data)
# - Test code creates ephemeral jobs via API when test.recording is True

# Random suffix for unique resource names
resource "random_id" "suffix" {
  byte_length = 4
}

# GCS bucket for input/output data
resource "google_storage_bucket" "batch_job_data" {
  name          = "c7n-vertex-batch-test-${random_id.suffix.hex}"
  location      = "US"
  force_destroy = true

  uniform_bucket_level_access = true
}

# Input data files for batch prediction
# Format: JSON Lines with instances
# Note: Run generate_test_data.py to create the input_data.jsonl file
# before applying this Terraform configuration
resource "google_storage_bucket_object" "input_data_us_central1" {
  name   = "input/us-central1/test_data.jsonl"
  bucket = google_storage_bucket.batch_job_data.name
  source = "${path.module}/input_data.jsonl"

  depends_on = [google_storage_bucket.batch_job_data]
}

resource "google_storage_bucket_object" "input_data_us_east1" {
  name   = "input/us-east1/test_data.jsonl"
  bucket = google_storage_bucket.batch_job_data.name
  source = "${path.module}/input_data.jsonl"

  depends_on = [google_storage_bucket.batch_job_data]
}

# Output values for use in tests
# Note: We don't need to create placeholder files in the output directories.
# The batch prediction job will create the output files when it runs.
output "bucket_name" {
  value       = google_storage_bucket.batch_job_data.name
  description = "Name of the GCS bucket for batch prediction data"
}

output "input_uri_us_central1" {
  value       = "gs://${google_storage_bucket.batch_job_data.name}/${google_storage_bucket_object.input_data_us_central1.name}"
  description = "GCS URI for input data in us-central1"
}

output "input_uri_us_east1" {
  value       = "gs://${google_storage_bucket.batch_job_data.name}/${google_storage_bucket_object.input_data_us_east1.name}"
  description = "GCS URI for input data in us-east1"
}

output "output_uri_us_central1" {
  value       = "gs://${google_storage_bucket.batch_job_data.name}/output/us-central1/"
  description = "GCS URI for output data in us-central1"
}

output "output_uri_us_east1" {
  value       = "gs://${google_storage_bucket.batch_job_data.name}/output/us-east1/"
  description = "GCS URI for output data in us-east1"
}

