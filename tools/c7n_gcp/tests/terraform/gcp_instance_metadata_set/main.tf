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

resource "google_compute_subnetwork" "network_subnet" {
  name          = "${random_pet.server.id}-subnet"
  ip_cidr_range = "10.2.0.0/16"
  network       = google_compute_network.vpc.name
  region        = "us-central1"
}

resource "google_compute_instance" "default" {
  name         = random_pet.server.id
  machine_type = "e2-micro"
  zone         = "us-central1-a"

  metadata = {
    c7n-test-key = "initial-value"
  }

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
    }
  }

  network_interface {
    network    = google_compute_network.vpc.name
    subnetwork = google_compute_subnetwork.network_subnet.name
    access_config {}
  }
}
