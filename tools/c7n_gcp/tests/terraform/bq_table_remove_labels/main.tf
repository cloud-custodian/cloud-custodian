provider "google" {
  # Keep the provider's goog-terraform-provisioned label off, so the only
  # labels present are the ones under test.
  add_terraform_attribution_label = false
}

resource "random_id" "suffix" {
  byte_length = 2
}

# The c7n_test label scopes parent dataset enumeration, keeping unrelated
# datasets out of the recording.
resource "google_bigquery_dataset" "dataset" {
  dataset_id                 = "c7n_remove_labels_tables_${random_id.suffix.hex}"
  delete_contents_on_destroy = true

  labels = {
    c7n_test = "bq_table_remove_labels"
  }
}

locals {
  schema = jsonencode([
    {
      name = "id"
      type = "INTEGER"
      mode = "REQUIRED"
    }
  ])
}

# Positive: removal with a surviving label, the case that silently no-op'd
# when removed keys were omitted from a merge-patch body.
resource "google_bigquery_table" "partial" {
  dataset_id          = google_bigquery_dataset.dataset.dataset_id
  table_id            = "partial"
  deletion_protection = false
  schema              = local.schema

  labels = {
    c7n_keep     = "yes"
    c7n_remove_a = "a"
    c7n_remove_b = "b"
  }
}

# Positive: every label removed.
resource "google_bigquery_table" "full" {
  dataset_id          = google_bigquery_dataset.dataset.dataset_id
  table_id            = "full"
  deletion_protection = false
  schema              = local.schema

  labels = {
    c7n_remove_a = "a"
    c7n_remove_b = "b"
  }
}

# Negative: none of the removed keys are present, labels must be untouched.
resource "google_bigquery_table" "absent" {
  dataset_id          = google_bigquery_dataset.dataset.dataset_id
  table_id            = "absent"
  deletion_protection = false
  schema              = local.schema

  labels = {
    c7n_keep = "yes"
  }
}
