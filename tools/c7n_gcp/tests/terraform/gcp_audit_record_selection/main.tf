variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project               = var.google_project_id
  billing_project       = var.google_project_id
  user_project_override = true
}

resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  name = "c7n-selection-${random_id.suffix.hex}"
}

resource "google_pubsub_topic" "audit" {
  name = "custodian-auto-audit-${local.name}"
}

# Seed a publisher binding so the subscriber can append its logging identity.
resource "google_service_account" "publisher" {
  account_id = local.name
}

resource "google_pubsub_topic_iam_member" "publisher" {
  topic  = google_pubsub_topic.audit.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.publisher.email}"
}

resource "google_compute_network" "vpc" {
  name                    = "${local.name}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "${local.name}-subnet"
  ip_cidr_range = "10.2.0.0/24"
  network       = google_compute_network.vpc.id
  region        = "us-central1"
}

resource "google_compute_instance" "default" {
  name         = local.name
  machine_type = "e2-micro"
  zone         = "us-central1-a"

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.subnet.id
  }
}
