variable "google_project_id" {
  description = "GCP project ID"
  type        = string
  nullable    = false
}

provider "google" {
  project = var.google_project_id
}

resource "google_bigquery_dataset" "dataset" {
  dataset_id = "c7n_bq_dataset"
  project    = var.google_project_id

  labels = {
    env      = "default"
    c7n_test = "bq_dataset_update"
  }
}

resource "google_bigquery_table" "table" {
  project             = var.google_project_id
  dataset_id          = google_bigquery_dataset.dataset.dataset_id
  table_id            = "c7n_bq_table"
  deletion_protection = false
  schema              = <<SCHEMA
  [
    {
      "name": "id",
      "type": "INTEGER",
      "mode": "REQUIRED"
    }
  ]
  SCHEMA

  labels = {
    env = "default"
  }
}
