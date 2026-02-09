variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
}

resource "google_bigquery_dataset" "dataset" {
  dataset_id = "c7n_bq_dataset"

  labels = {
    env = "default"
  }
}

resource "google_bigquery_table" "table" {
  dataset_id = google_bigquery_dataset.dataset.dataset_id
  table_id   = "c7n_bq_table"
  schema     = <<SCHEMA
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
