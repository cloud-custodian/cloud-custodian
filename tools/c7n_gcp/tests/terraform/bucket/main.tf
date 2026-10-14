provider "google" {}

resource "google_storage_bucket" "bucket" {
  name     = "c7n-bucket"
  location = "US"

  labels = {
    env = "default"
  }
}
