resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_compute_target_pool" "default" {
  name   = "c7n-target-pool-${terraform.workspace}-${random_id.suffix.hex}"
  region = "us-central1"
}

resource "google_compute_forwarding_rule" "default" {
  name        = "c7n-forwarding-rule-${terraform.workspace}-${random_id.suffix.hex}"
  region      = "us-central1"
  target      = google_compute_target_pool.default.id
  port_range  = "80"
  ip_protocol = "TCP"

  labels = {
    env = "default"
  }
}
