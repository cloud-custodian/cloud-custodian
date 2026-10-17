provider "google" {}

resource "google_bigquery_dataset" "dataset" {
  dataset_id  = "c7n_bq_set_access"
  description = "c7n set-access test"

  labels = {
    c7n_test = "bq_dataset_set_access"
  }

  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }

  access {
    role          = "READER"
    special_group = "projectReaders"
  }

  access {
    role          = "READER"
    special_group = "allAuthenticatedUsers"
  }

  access {
    role       = "READER"
    iam_member = "allUsers"
  }
}
