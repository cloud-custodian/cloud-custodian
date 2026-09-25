provider "google" {
  # Keep the provider's goog-terraform-provisioned label off, so the only
  # labels present are the ones under test.
  add_terraform_attribution_label = false
}

resource "random_id" "suffix" {
  byte_length = 2
}

# Positive: removal with a surviving label, the case that silently no-op'd
# when removed keys were omitted from a merge-patch body.
resource "google_sql_database_instance" "partial" {
  name                = "c7n-remove-labels-partial-${random_id.suffix.hex}"
  database_version    = "MYSQL_8_0"
  region              = "us-central1"
  deletion_protection = false

  settings {
    tier = "db-f1-micro"

    user_labels = {
      c7n_keep     = "yes"
      c7n_remove_a = "a"
      c7n_remove_b = "b"
    }
  }
}

# Positive: every label removed.
resource "google_sql_database_instance" "full" {
  name                = "c7n-remove-labels-full-${random_id.suffix.hex}"
  database_version    = "MYSQL_8_0"
  region              = "us-central1"
  deletion_protection = false

  settings {
    tier = "db-f1-micro"

    user_labels = {
      c7n_remove_a = "a"
      c7n_remove_b = "b"
    }
  }
}

# Negative: none of the removed keys are present, labels must be untouched.
resource "google_sql_database_instance" "absent" {
  name                = "c7n-remove-labels-absent-${random_id.suffix.hex}"
  database_version    = "MYSQL_8_0"
  region              = "us-central1"
  deletion_protection = false

  settings {
    tier = "db-f1-micro"

    user_labels = {
      c7n_keep = "yes"
    }
  }
}
