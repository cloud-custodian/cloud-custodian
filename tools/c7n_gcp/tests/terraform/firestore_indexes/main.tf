variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
}

resource "random_pet" "db" {
  prefix = "c7nidx"
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

resource "google_firestore_index" "c7n" {
  project     = var.google_project_id
  database    = google_firestore_database.c7n.name
  collection  = "orders"
  query_scope = "COLLECTION"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }

  fields {
    field_path = "createdAt"
    order      = "DESCENDING"
  }
}

resource "google_firestore_index" "c7n_east" {
  project     = var.google_project_id
  database    = google_firestore_database.c7n_east.name
  collection  = "orders"
  query_scope = "COLLECTION_GROUP"

  fields {
    field_path = "status"
    order      = "ASCENDING"
  }

  fields {
    field_path = "createdAt"
    order      = "DESCENDING"
  }
}
