provider "google" {
  # Keep the provider's goog-terraform-provisioned label off, so the only
  # labels present are the ones under test.
  add_terraform_attribution_label = false
}

resource "random_id" "suffix" {
  byte_length = 2
}

# The c7n_test label scopes the policy's server-side dataset query, keeping
# unrelated datasets out of the recording.

# Positive: removal with surviving labels, the case that silently no-op'd
# when removed keys were omitted from a merge-patch body.
resource "google_bigquery_dataset" "partial" {
  dataset_id                 = "c7n_remove_labels_partial_${random_id.suffix.hex}"
  delete_contents_on_destroy = true

  labels = {
    c7n_test     = "bq_dataset_remove_labels"
    c7n_keep     = "yes"
    c7n_remove_a = "a"
    c7n_remove_b = "b"
  }
}

# Negative: none of the removed keys are present, labels must be untouched.
resource "google_bigquery_dataset" "absent" {
  dataset_id                 = "c7n_remove_labels_absent_${random_id.suffix.hex}"
  delete_contents_on_destroy = true

  labels = {
    c7n_test = "bq_dataset_remove_labels"
    c7n_keep = "yes"
  }
}

# Positive: every label removed. Carries only its own query label, since a
# shared c7n_test label would survive the removal.
resource "google_bigquery_dataset" "full" {
  dataset_id                 = "c7n_remove_labels_full_${random_id.suffix.hex}"
  delete_contents_on_destroy = true

  labels = {
    c7n_remove_full = "yes"
  }
}
