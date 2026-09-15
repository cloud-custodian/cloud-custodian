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

resource "google_compute_network" "vpc" {
  name                    = "${random_pet.server.id}-vpc"
  auto_create_subnetworks = "false"
  routing_mode            = "GLOBAL"
}

resource "google_compute_subnetwork" "default" {
  name          = "${random_pet.server.id}-subnet"
  ip_cidr_range = "10.2.0.0/16"
  network       = google_compute_network.vpc.name
  region        = "us-central1"
  # flow logging is disabled by default — the test enables it via the action
}
