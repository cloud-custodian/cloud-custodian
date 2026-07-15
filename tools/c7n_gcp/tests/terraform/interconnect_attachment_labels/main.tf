resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_compute_network" "c7n_test_network" {
  name                    = "c7n-ia-net-${terraform.workspace}-${random_id.suffix.hex}"
  auto_create_subnetworks = false
}

resource "google_compute_router" "c7n_test_router" {
  name    = "c7n-ia-router-${terraform.workspace}-${random_id.suffix.hex}"
  network = google_compute_network.c7n_test_network.name
  region  = "us-central1"

  bgp {
    asn = 16550
  }
}

resource "google_compute_interconnect_attachment" "c7n_test_attachment" {
  name                     = "c7n-ia-${terraform.workspace}-${random_id.suffix.hex}"
  region                   = "us-central1"
  router                   = google_compute_router.c7n_test_router.id
  type                     = "PARTNER"
  edge_availability_domain = "AVAILABILITY_DOMAIN_1"
  admin_enabled            = true

  labels = {
    env = "default"
  }
}
