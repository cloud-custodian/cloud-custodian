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
  machine_type = "e2-medium"
  zone         = "us-central1-a"
  tags         = ["foo", "bar"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      labels = {
        my_label = "value"
      }
    }
  }

  network_interface {
    network    = google_compute_network.vpc.name
    subnetwork = google_compute_subnetwork.network_subnet.name
    access_config {}
  }
}
