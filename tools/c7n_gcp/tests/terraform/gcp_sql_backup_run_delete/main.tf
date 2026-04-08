variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project               = var.google_project_id
  billing_project       = var.google_project_id
  user_project_override = true
}

resource "random_pet" "server" {
}

resource "google_sql_database_instance" "default" {
  name                = random_pet.server.id
  database_version    = "MYSQL_8_0"
  region              = "us-central1"
  deletion_protection = false

  settings {
    tier = "db-f1-micro"

    backup_configuration {
      enabled = true
    }
  }
}
