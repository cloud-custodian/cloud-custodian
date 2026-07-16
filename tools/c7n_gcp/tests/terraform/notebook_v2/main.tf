provider "google" {}

resource "random_id" "suffix" {
  byte_length = 2
}

resource "google_workbench_instance" "private_instance" {
  name     = "c7n-notebook-private-${terraform.workspace}-${random_id.suffix.hex}"
  location = "us-central1-a"

  gce_setup {
    disable_public_ip = true
  }
}

resource "google_workbench_instance" "public_instance" {
  name     = "c7n-notebook-public-${terraform.workspace}-${random_id.suffix.hex}"
  location = "us-central1-a"

  gce_setup {
    disable_public_ip = false
  }
}
