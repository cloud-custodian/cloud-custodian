variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
}

resource "google_storage_bucket" "no_rules" {
  name                        = "c7n-lifecycle-none-5l0j5kqp"
  location                    = "US"
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "other_rules" {
  name                        = "c7n-lifecycle-other-5l0j5kqp"
  location                    = "US"
  force_destroy               = true
  uniform_bucket_level_access = true

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 120
    }
  }

  lifecycle_rule {
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
    condition {
      age            = 30
      matches_prefix = ["logs/"]
    }
  }
}

resource "google_storage_bucket" "same_rule" {
  name                        = "c7n-lifecycle-same-5l0j5kqp"
  location                    = "US"
  force_destroy               = true
  uniform_bucket_level_access = true

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 90
    }
  }
}
