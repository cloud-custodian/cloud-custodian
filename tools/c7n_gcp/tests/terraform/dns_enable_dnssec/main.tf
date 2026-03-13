variable "google_project_id" {
  description = "GCP project ID"
}

provider "google" {
  project = var.google_project_id
}

resource "google_dns_managed_zone" "public_zone" {
  name     = "c7n-dnssec-test-zone"
  dns_name = "c7n-dnssec-test.example.com."

  visibility = "public"

  dnssec_config {
    state = "off"
  }
}
