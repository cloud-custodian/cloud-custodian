variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
}

resource "random_pet" "db" {
  prefix = "c7nfld"
  length = 1
}

resource "google_firestore_database" "c7n" {
  project                 = var.google_project_id
  name                    = random_pet.db.id
  location_id             = "us-central1"
  type                    = "FIRESTORE_NATIVE"
  deletion_policy         = "DELETE"
  delete_protection_state = "DELETE_PROTECTION_DISABLED"
}

resource "google_firestore_database" "c7n_east" {
  project                 = var.google_project_id
  name                    = "${random_pet.db.id}-east"
  location_id             = "us-east1"
  type                    = "FIRESTORE_NATIVE"
  deletion_policy         = "DELETE"
  delete_protection_state = "DELETE_PROTECTION_DISABLED"
}

resource "google_firestore_field" "c7n_ttl" {
  project    = var.google_project_id
  database   = google_firestore_database.c7n.name
  collection = "orders"
  field      = "expireAt"

  ttl_config {}
}

resource "google_firestore_field" "c7n_east_ttl" {
  project    = var.google_project_id
  database   = google_firestore_database.c7n_east.name
  collection = "orders"
  field      = "expireAt"

  ttl_config {}
}
