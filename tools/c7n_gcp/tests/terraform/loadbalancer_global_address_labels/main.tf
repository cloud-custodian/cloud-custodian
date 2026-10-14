resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_compute_global_address" "default" {
  name = "c7n-global-address-${terraform.workspace}-${random_id.suffix.hex}"

  labels = {
    env = "default"
  }
}
