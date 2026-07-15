provider "google" {}

resource "google_compute_network" "policy_network" {
  name                    = "c7n-dns-policy-network"
  auto_create_subnetworks = false
}

resource "google_dns_policy" "default" {
  name           = "c7n-dns-policy-update-test"
  enable_logging = false

  networks {
    network_url = google_compute_network.policy_network.id
  }
}
