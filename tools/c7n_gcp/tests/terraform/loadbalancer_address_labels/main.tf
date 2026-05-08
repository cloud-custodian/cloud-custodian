resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_compute_address" "default" {
  name   = "c7n-address-${terraform.workspace}-${random_id.suffix.hex}"
  region = "us-central1"

  labels = {
    env = "default"
  }
}
