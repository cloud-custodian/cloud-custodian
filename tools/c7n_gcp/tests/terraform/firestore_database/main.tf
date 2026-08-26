variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
}

resource "random_pet" "db" {
  prefix = "c7nfs"
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

resource "google_firestore_backup_schedule" "c7n" {
  project   = var.google_project_id
  database  = google_firestore_database.c7n.name
  retention = "1209600s"

  daily_recurrence {}
}

resource "google_firestore_backup_schedule" "c7n_east" {
  project   = var.google_project_id
  database  = google_firestore_database.c7n_east.name
  retention = "604800s"

  daily_recurrence {}
}
